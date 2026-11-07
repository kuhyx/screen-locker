"""An armed lock takes itself down when wake-alarm's signed carrot lands late.

2026-11-07: the lock armed at 07:49 because today's morning_session.json had
not landed; it landed at 07:50 and nothing re-read it, so the morning session
ran under a fullscreen lock.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock.log_integrity import compute_entry_hmac
import pytest

from screen_locker import _carrot_watch, _morning_session
from screen_locker._carrot_watch import POLL_MS, watch_for_carrot
from screen_locker._morning_session import MorningSkip
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_EIGHT = datetime(2026, 11, 7, 8, 0).astimezone()


@pytest.fixture(autouse=True)
def _signing_key(tmp_path: Path) -> Iterator[None]:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key):
        yield


def _sign(date: str, until: datetime) -> None:
    """Write a signed session file into the conftest-redirected path."""
    entry: dict[str, object] = {
        "date": date,
        "outcome": "in_progress",
        "exempt_until": until.isoformat(),
    }
    entry["hmac"] = compute_entry_hmac(entry)
    _morning_session.MORNING_SESSION_FILE.write_text(json.dumps(entry))


def _tick(now: datetime) -> tuple[MagicMock, MagicMock]:
    """Arm the watch, run its first poll at ``now``; return (root, on_carrot)."""
    root, on_carrot = MagicMock(), MagicMock()
    watch_for_carrot(root, on_carrot)
    with patch.object(_carrot_watch, "_local_now", return_value=now):
        root.after.call_args.args[1]()
    return root, on_carrot


class TestWatchForCarrot:
    """The poll on the Tk loop."""

    def test_local_now_is_timezone_aware_local_time(self) -> None:
        """The poll's clock is the real, aware local time."""
        assert abs(_carrot_watch._local_now() - datetime.now().astimezone()) < (
            timedelta(seconds=5)
        )

    def test_arms_a_fifteen_second_poll(self) -> None:
        """Arming schedules the first check 15 s out and releases nothing."""
        root, on_carrot = MagicMock(), MagicMock()
        watch_for_carrot(root, on_carrot)
        assert POLL_MS == 15_000
        assert root.after.call_args.args[0] == POLL_MS
        on_carrot.assert_not_called()

    def test_signed_todays_skip_releases_once_and_stops_polling(self) -> None:
        """A skip that landed after arming is handed over; no re-arm."""
        until = _EIGHT + timedelta(hours=1, minutes=13)
        _sign("2026-11-07", until)
        root, on_carrot = _tick(_EIGHT)
        on_carrot.assert_called_once_with(MorningSkip("in_progress", until))
        assert root.after.call_count == 1

    def test_no_file_keeps_the_lock_and_reschedules(self) -> None:
        """No file: the lock stays and the next poll is scheduled."""
        root, on_carrot = _tick(_EIGHT)
        on_carrot.assert_not_called()
        assert root.after.call_count == 2
        assert root.after.call_args.args[0] == POLL_MS

    def test_expired_skip_keeps_the_lock(self) -> None:
        """A carrot whose exempt_until has passed is no skip."""
        _sign("2026-11-07", _EIGHT - timedelta(minutes=1))
        root, on_carrot = _tick(_EIGHT)
        on_carrot.assert_not_called()
        assert root.after.call_count == 2

    def test_yesterdays_file_keeps_the_lock(self) -> None:
        """A file dated another day is no skip."""
        _sign("2026-11-06", _EIGHT + timedelta(hours=3))
        _root, on_carrot = _tick(_EIGHT)
        on_carrot.assert_not_called()

    @pytest.mark.parametrize(("hour", "minute"), [(4, 59), (11, 0), (23, 30)])
    def test_outside_05_to_11_never_reads_or_releases(
        self, hour: int, minute: int
    ) -> None:
        """Outside 05:00-11:00 local the poll neither reads nor releases."""
        now = _EIGHT.replace(hour=hour, minute=minute)
        _sign("2026-11-07", now + timedelta(hours=1))
        with patch.object(_carrot_watch._morning_session, "morning_skip_today") as read:
            root, on_carrot = _tick(now)
        read.assert_not_called()
        on_carrot.assert_not_called()
        assert root.after.call_count == 2

    def test_inside_window_reads_without_waiting(self) -> None:
        """The poll never waits: it must not block the Tk loop."""
        with patch.object(
            _carrot_watch._morning_session, "morning_skip_today", return_value=None
        ) as read:
            _tick(_EIGHT)
        read.assert_called_once_with(_EIGHT, wait=False)

    def test_reader_failure_is_logged_and_the_poll_survives(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A read error warns and re-arms; one bad read must not end the watch."""
        with (
            patch.object(
                _carrot_watch._morning_session,
                "morning_skip_today",
                side_effect=OSError("disk gone"),
            ),
            caplog.at_level(logging.WARNING, logger="screen_locker._carrot_watch"),
        ):
            root, on_carrot = _tick(_EIGHT)
        on_carrot.assert_not_called()
        assert root.after.call_count == 2
        assert "disk gone" in caplog.text


class TestLockerStandsDown:
    """The locker side: marker, decision, warning, then the real close."""

    def test_construction_arms_the_watch(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """A built locker watches on its own root and its own stand-down."""
        with patch("screen_locker.screen_lock.watch_for_carrot") as watch:
            locker = create_locker(mock_tk, tmp_path)
        watch.assert_called_once_with(locker.root, locker._stand_down_for_carrot)

    def test_stand_down_banks_marker_records_decision_then_closes(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Marker first, decision lock=no, warning, and only then close()."""
        locker = create_locker(mock_tk, tmp_path)
        until = _EIGHT + timedelta(hours=1)
        order = MagicMock()
        with (
            patch.object(locker, "_save_early_bird_pending", order.save),
            patch("screen_locker._auto_upgrade.record_decision", order.record),
            patch.object(locker, "close", order.close),
            caplog.at_level(logging.WARNING, logger="screen_locker._auto_upgrade"),
        ):
            locker._stand_down_for_carrot(MorningSkip("in_progress", until))
        assert [c[0] for c in order.mock_calls] == ["save", "record", "close"]
        decision = order.record.call_args.args[0]
        assert decision.locked is False
        assert decision.reason == "wake_alarm_skip_late"
        assert decision.extra["exempt_until"] == until.isoformat()
        assert decision.extra["outcome"] == "in_progress"
        assert "carrot" in caplog.text.lower()

    def test_stand_down_goes_through_the_real_close_and_exits_zero(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The real ``close``: lock window released, instance lock dropped, exit 0."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_save_early_bird_pending"),
            patch("screen_locker._auto_upgrade.record_decision"),
            patch.object(locker, "_lock") as lock,
            patch.object(locker._instance_lock, "release") as release,
        ):
            locker._stand_down_for_carrot(MorningSkip("completed", _EIGHT))
        lock.close.assert_called_once_with()
        release.assert_called_once_with()
        mock_sys_exit.assert_called_once_with(0)
