"""An open lock window closes itself when another process credits today.

2026-11-16: the window opened 07:55:17; the `_session_stream` daemon credited a
manual workout at 07:59:04 and the open window never noticed -- TRY AGAIN only
asked StrongLifts/ADB/HTTP -- so kuhy had to mark a sick day to get out.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import ANY, MagicMock, patch

import pytest

from screen_locker._credit_watch import POLL_MS, watch_for_credit
from screen_locker._day import today_str
from screen_locker._log_mixin import write_signed_entry
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _signing_key(tmp_path: Path) -> Iterator[None]:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key):
        yield


def _credit_today(log_file: Path) -> None:
    """What the stream daemon does: a signed row for today in the scratch log."""
    write_signed_entry(
        log_file,
        today_str(),
        {"type": "manual", "workout_id": "wk-1", "source": "phone"},
    )


def _arm(
    log_file: Path, *, logged: bool = False
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Arm the watch; return (root, on_credit, has_logged)."""
    root, on_credit = MagicMock(), MagicMock()
    has_logged = MagicMock(return_value=logged)
    watch_for_credit(root, log_file, has_logged, on_credit)
    return root, on_credit, has_logged


def _fire(root: MagicMock) -> None:
    """Run the poll the watch last scheduled."""
    root.after.call_args.args[1]()


class TestWatchForCredit:
    """The poll on the Tk loop."""

    def test_polls_well_inside_ten_seconds(self, tmp_path: Path) -> None:
        """First check is scheduled at most 5 s out: credit shows in <= 10 s."""
        root, on_credit, _ = _arm(tmp_path / "log.json")
        assert POLL_MS <= 5_000
        assert root.after.call_args.args[0] == POLL_MS
        on_credit.assert_not_called()

    def test_nothing_logged_keeps_the_window_and_rearms(self, tmp_path: Path) -> None:
        """No file, no credit: the window stays and the next poll is armed."""
        root, on_credit, _ = _arm(tmp_path / "log.json")
        _fire(root)
        on_credit.assert_not_called()
        assert root.after.call_count == 2

    def test_credit_landing_after_arming_fires_once_and_stops(
        self, tmp_path: Path
    ) -> None:
        """A row written after arming is handed over; the poll is not re-armed."""
        log_file = tmp_path / "log.json"
        root = MagicMock()
        on_credit = MagicMock()
        watch_for_credit(root, log_file, log_file.exists, on_credit)
        _fire(root)
        on_credit.assert_not_called()
        _credit_today(log_file)
        _fire(root)
        on_credit.assert_called_once_with()
        assert root.after.call_count == 2

    def test_unchanged_file_is_not_reread(self, tmp_path: Path) -> None:
        """Steady state is one stat per poll: the log is parsed only on change."""
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        root, _, has_logged = _arm(log_file)
        _fire(root)
        _fire(root)
        _fire(root)
        assert has_logged.call_count == 1

    def test_rewritten_file_is_reread(self, tmp_path: Path) -> None:
        """A changed file is checked again even if the first check said no."""
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        root, _, has_logged = _arm(log_file)
        _fire(root)
        log_file.write_text('{"1999-01-01": []}')
        _fire(root)
        assert has_logged.call_count == 2

    def test_credit_present_before_first_poll_is_caught(self, tmp_path: Path) -> None:
        """A row that landed between startup and arming is not missed."""
        log_file = tmp_path / "log.json"
        _credit_today(log_file)
        root, on_credit, _ = _arm(log_file, logged=True)
        _fire(root)
        on_credit.assert_called_once_with()

    def test_read_failure_is_logged_and_the_poll_survives(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failing check warns and re-arms; it must not end the only watcher."""
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        root, on_credit, has_logged = _arm(log_file)
        has_logged.side_effect = OSError("disk gone")
        with caplog.at_level(logging.WARNING, logger="screen_locker._credit_watch"):
            _fire(root)
        on_credit.assert_not_called()
        assert root.after.call_count == 2
        assert "disk gone" in caplog.text

    def test_unreadable_stat_is_logged_not_swallowed(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A log that exists but cannot be stat'ed is reported, not skipped."""
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        root, on_credit, _ = _arm(log_file)
        with (
            patch("pathlib.Path.stat", side_effect=PermissionError("no stat")),
            caplog.at_level(logging.WARNING, logger="screen_locker._credit_watch"),
        ):
            _fire(root)
        on_credit.assert_not_called()
        assert "no stat" in caplog.text
        assert root.after.call_count == 2


class TestLockerClosesOnCredit:
    """The locker side: wiring, the retry path and the stand-down itself."""

    def test_construction_arms_the_watch(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """A built locker watches its own log, with its own stand-down."""
        with patch("screen_locker.screen_lock.watch_for_credit") as watch:
            locker = create_locker(mock_tk, tmp_path)
        watch.assert_called_once_with(
            locker.root,
            locker.log_file,
            ANY,  # create_locker patches has_logged_today during construction
            locker._stand_down_for_credit,
        )

    def test_open_window_closes_when_another_process_credits(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Window open -> row appended to the scratch log -> next poll closes it."""
        locker = create_locker(mock_tk, tmp_path)
        root = MagicMock()
        watch_for_credit(
            root,
            locker.log_file,
            locker.has_logged_today,
            locker._stand_down_for_credit,
        )
        _fire(root)
        mock_sys_exit.assert_not_called()
        _credit_today(locker.log_file)
        with (
            patch.object(locker, "_lock") as lock,
            patch("screen_locker._credit_watch.record_decision") as record,
        ):
            _fire(root)
        lock.close.assert_called_once_with()
        mock_sys_exit.assert_called_once_with(0)
        decision = record.call_args.args[0]
        assert decision.locked is False
        assert decision.reason == "workout_credited_elsewhere"

    def test_stand_down_writes_no_credit_of_its_own(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Closing must not double-credit: no new log row, no credit applied."""
        locker = create_locker(mock_tk, tmp_path)
        _credit_today(locker.log_file)
        before = locker.log_file.read_bytes()
        with (
            patch.object(locker, "_lock"),
            patch.object(locker, "_apply_workout_credit") as credit,
        ):
            locker._stand_down_for_credit()
        credit.assert_not_called()
        assert locker.log_file.read_bytes() == before
        mock_sys_exit.assert_called_once_with(0)

    def test_try_again_with_todays_credit_closes_instead_of_asking_the_phone(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """2026-11-16: TRY AGAIN said 'stale' though the log held today's row."""
        locker = create_locker(mock_tk, tmp_path)
        _credit_today(locker.log_file)
        with (
            patch.object(locker, "_lock"),
            patch.object(locker, "_verify_phone_workout") as verify,
        ):
            locker._start_phone_check()
        verify.assert_not_called()
        mock_sys_exit.assert_called_once_with(0)

    def test_try_again_without_credit_still_asks_the_phone(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Not logged today: the retry runs the normal phone check."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker, "_verify_phone_workout", return_value=("stale", "old")
        ) as verify:
            locker._start_phone_check()
            locker._phone_future.result(timeout=5)
        verify.assert_called_once_with()
        mock_sys_exit.assert_not_called()
