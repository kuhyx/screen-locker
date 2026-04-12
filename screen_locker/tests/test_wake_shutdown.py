"""Tests for rtcwake integration in ShutdownMixin."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestIsTomorrowAlarmDay:
    """Tests for _is_tomorrow_alarm_day."""

    def test_sunday_evening_means_monday_alarm(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Sunday evening → Monday is alarm day (weekday=0)."""
        locker = create_locker(mock_tk, tmp_path)
        from datetime import datetime, timezone

        # Sunday 2026-04-12 → tomorrow Monday
        with patch(
            "python_pkg.screen_locker._shutdown.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 12, 23, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = datetime
            from datetime import timedelta

            # Ensure timedelta works
            with patch(
                "python_pkg.screen_locker._shutdown.timedelta",
                timedelta,
            ):
                assert locker._is_tomorrow_alarm_day() is True

    def test_monday_evening_is_not_alarm_next(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Monday evening → Tuesday is NOT an alarm day."""
        locker = create_locker(mock_tk, tmp_path)
        from datetime import datetime, timedelta, timezone

        # Monday 2026-04-13 → tomorrow Tuesday (weekday=1)
        with (
            patch(
                "python_pkg.screen_locker._shutdown.datetime",
            ) as mock_dt,
            patch(
                "python_pkg.screen_locker._shutdown.timedelta",
                timedelta,
            ),
        ):
            mock_dt.now.return_value = datetime(2026, 4, 13, 23, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = datetime
            assert locker._is_tomorrow_alarm_day() is False

    def test_thursday_evening_friday_is_alarm(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Thursday evening → Friday is alarm day (weekday=4)."""
        locker = create_locker(mock_tk, tmp_path)
        from datetime import datetime, timedelta, timezone

        # Thursday 2026-04-16 → tomorrow Friday (weekday=4)
        with (
            patch(
                "python_pkg.screen_locker._shutdown.datetime",
            ) as mock_dt,
            patch(
                "python_pkg.screen_locker._shutdown.timedelta",
                timedelta,
            ),
        ):
            mock_dt.now.return_value = datetime(2026, 4, 16, 23, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = datetime
            assert locker._is_tomorrow_alarm_day() is True


class TestScheduleRtcwake:
    """Tests for _schedule_rtcwake."""

    def test_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Successful rtcwake call returns True."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "python_pkg.screen_locker._shutdown.subprocess.run",
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert locker._schedule_rtcwake() is True
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "rtcwake" in cmd[1]

    def test_failure_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Failed rtcwake call returns False."""
        locker = create_locker(mock_tk, tmp_path)
        import subprocess

        with patch(
            "python_pkg.screen_locker._shutdown.subprocess.run",
            side_effect=subprocess.SubprocessError("rtcwake failed"),
        ):
            assert locker._schedule_rtcwake() is False


class TestScheduleWakeIfNeeded:
    """Tests for schedule_wake_if_needed."""

    def test_skips_when_not_alarm_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when tomorrow is not an alarm day."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_is_tomorrow_alarm_day", return_value=False):
            assert locker.schedule_wake_if_needed() is False

    def test_schedules_when_alarm_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns True when tomorrow is an alarm day and rtcwake succeeds."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_tomorrow_alarm_day", return_value=True),
            patch.object(locker, "_schedule_rtcwake", return_value=True),
        ):
            assert locker.schedule_wake_if_needed() is True

    def test_returns_false_when_rtcwake_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when rtcwake call fails."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_tomorrow_alarm_day", return_value=True),
            patch.object(locker, "_schedule_rtcwake", return_value=False),
        ):
            assert locker.schedule_wake_if_needed() is False


class TestComputeWakeTimestamp:
    """Tests for _compute_wake_timestamp."""

    def test_returns_future_epoch(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Wake timestamp is roughly 8 hours from now."""
        locker = create_locker(mock_tk, tmp_path)
        import time

        now = int(time.time())
        wake = locker._compute_wake_timestamp()
        # Should be ~8 hours ahead (within 60 second tolerance)
        expected = now + 8 * 3600
        assert abs(wake - expected) < 60
