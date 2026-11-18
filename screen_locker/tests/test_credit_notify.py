"""The "Workout credited" desktop notification and every way it can fail.

The autouse ``_no_desktop_notifications`` fixture stubs
``notify_workout_credit`` for the whole suite; the real one is captured here
at import time, before any fixture runs.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker import _credit_notify
from screen_locker.tests.conftest import create_locker

# The toast's glyphs (textgate): the module's own constants, not words.
_SHUTDOWN = _credit_notify._SHUTDOWN

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_real_notify = _credit_notify.notify_workout_credit
_FRIDAY = "2026-10-09"  # Thu-Sun: tonight is the second config field
_MOD = "screen_locker._credit_notify"


@pytest.fixture(autouse=True)
def _fixed_day() -> Iterator[None]:
    with patch(f"{_MOD}.today_str", return_value=_FRIDAY):
        yield


def _warned(caplog: pytest.LogCaptureFixture, needle: str) -> bool:
    return any(
        r.levelno >= logging.WARNING and needle in r.getMessage()
        for r in caplog.records
    )


class TestCreditBody:
    """Whichever parts are known end up in the body."""

    def test_full_body(self) -> None:
        """Shutdown time and tonight's move; no gaming figure any more."""
        body = _credit_notify.credit_body((0, 1200, 0), (0, 1320, 0))
        assert body == f"{_SHUTDOWN} 22:00 (+2h)"

    def test_a_capped_credit_shows_plus_zero(self) -> None:
        """No backwards move is ever shown: the delta floors at zero."""
        body = _credit_notify.credit_body((0, 1380, 0), (0, 1320, 0))
        assert body == f"{_SHUTDOWN} 22:00 (+0h)"

    def test_a_late_credit_shows_the_reward_not_the_jump(self) -> None:
        """18:00 -> 21:58 after a run ending 19:58: the toast says +2h, not +3h58m."""
        body = _credit_notify.credit_body((0, 1080, 0), (0, 1318, 0), reward=120)
        assert body == f"{_SHUTDOWN} 21:58 (+2h)"

    def test_a_ceiling_cut_reward_shows_what_was_left(self) -> None:
        """A 2h reward that met the 23:00 ceiling after 1h shows +1h."""
        body = _credit_notify.credit_body((0, 1320, 0), (0, 1380, 0), reward=120)
        assert body == f"{_SHUTDOWN} 23:00 (+1h)"

    def test_unknown_before_drops_the_delta(self) -> None:
        """Without the old config there is no move to show."""
        assert _credit_notify.credit_body(None, (0, 1320, 0)) == f"{_SHUTDOWN} 22:00"

    def test_unreadable_after_warns_and_shows_the_check_mark(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unreadable config is said out loud, not silently omitted."""
        assert _credit_notify.credit_body(None, None) == "\N{CHECK MARK}"
        assert _warned(caplog, "unreadable")

    def test_the_gaming_figure_is_gone(self) -> None:
        """No budget exists any more: the body never mentions gaming."""
        assert not hasattr(_credit_notify, "gaming_minutes_today")
        assert not hasattr(_credit_notify, "_GAMING")


class TestSendNotification:
    """notify-send's every failure is a warning and a False."""

    def test_missing_binary(self, caplog: pytest.LogCaptureFixture) -> None:
        """No notify-send on PATH."""
        with patch(f"{_MOD}.shutil.which", return_value=None):
            assert not _credit_notify.send_notification("t", "b")
        assert _warned(caplog, "notify-send not found")

    @pytest.mark.parametrize(
        "error", [OSError("exec"), subprocess.TimeoutExpired("notify-send", 5)]
    )
    def test_spawn_failure_or_hang(
        self, error: Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An exec error or a DBus hang past the timeout."""
        with (
            patch(f"{_MOD}.shutil.which", return_value="/usr/bin/notify-send"),
            patch(f"{_MOD}.subprocess.run", side_effect=error),
        ):
            assert not _credit_notify.send_notification("t", "b")
        assert _warned(caplog, "Desktop notification failed")

    @pytest.mark.parametrize(
        ("stderr", "shown"),
        [("no bus", "no bus"), ("  ", "is a DBus session reachable")],
    )
    def test_nonzero_exit(
        self, stderr: str, shown: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failing notify-send names its stderr, or the likely cause."""
        done = subprocess.CompletedProcess([], 1, stdout="", stderr=stderr)
        with (
            patch(f"{_MOD}.shutil.which", return_value="/usr/bin/notify-send"),
            patch(f"{_MOD}.subprocess.run", return_value=done),
        ):
            assert not _credit_notify.send_notification("t", "b")
        assert _warned(caplog, shown)

    def test_success(self) -> None:
        """Exit 0 is the only True."""
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with (
            patch(f"{_MOD}.shutil.which", return_value="/usr/bin/notify-send"),
            patch(f"{_MOD}.subprocess.run", return_value=done) as run,
        ):
            assert _credit_notify.send_notification("Title", "Body")
        assert run.call_args.args[0] == [
            "/usr/bin/notify-send",
            "--app-name=screen-locker",
            "Title",
            "Body",
        ]


def test_notify_workout_credit_sends_the_composed_body() -> None:
    """The real entry point composes the body and sends it once."""
    with (
        patch(f"{_MOD}.send_notification", return_value=True) as send,
    ):
        assert _real_notify((0, 1080, 0), (0, 1318, 0), 120)
    send.assert_called_once_with(_credit_notify.TITLE, f"{_SHUTDOWN} 21:58 (+2h)")


class TestCreditSideOfTheNotifier:
    """The credit mixin's guards around the notifier."""

    def test_a_raising_notifier_never_fails_the_credit(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Anything the notifier raises is logged at ERROR and dropped."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(f"{_MOD}.notify_workout_credit", side_effect=KeyError("x")):
            locker._notify_credit(None, None, None)
        assert any(
            r.levelno == logging.ERROR and "notification failed" in r.getMessage()
            for r in caplog.records
        )

    def test_uncounted_type_never_moves_the_shutdown(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The first-unit push refuses a type that earns no credit."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "early_bird"}
        adjust = MagicMock(return_value=True)
        object.__setattr__(locker, "_adjust_shutdown_time_later", adjust)
        assert locker._try_adjust_shutdown_for_workout() is False
        adjust.assert_not_called()
