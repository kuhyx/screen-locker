"""Tests for weekly workout enforcement and relaxed-day (Tue-Thu) logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import (
    create_locker,
    create_locker_relaxed_day,
)

# ---------------------------------------------------------------------------
# _check_non_verify_exits: relaxed-day branch
# ---------------------------------------------------------------------------


class TestRelaxedDayBranch:
    """RelaxedDayBranch."""

    def test_relaxed_day_sets_flag_instead_of_exiting(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Relaxed day sets flag instead of exiting."""
        locker = create_locker_relaxed_day(mock_tk, tmp_path)
        assert locker._relaxed_day_mode is True
        mock_sys_exit.assert_not_called()

    def test_relaxed_day_calls_start_relaxed_flow(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Relaxed day calls start relaxed flow."""
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum",
                return_value=False,
            ),
            patch.object(ScreenLocker, "_start_phone_check") as mock_phone,
            patch.object(ScreenLocker, "_start_relaxed_day_flow") as mock_relaxed,
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_relaxed.assert_called_once()
        mock_phone.assert_not_called()

    def test_relaxed_day_uses_small_window_not_fullscreen(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Relaxed day uses small window not fullscreen."""
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum",
                return_value=False,
            ),
            patch("screen_locker.screen_lock.LockWindow") as mock_lock_window,
            patch.object(ScreenLocker, "_setup_relaxed_day_window") as mock_small,
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_relaxed_day_flow"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_small.assert_called_once()
        mock_lock_window.assert_not_called()

    def test_relaxed_day_no_grab_input(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Relaxed day no grab input."""
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum",
                return_value=False,
            ),
            patch("screen_locker.screen_lock.LockWindow") as mock_lock_window,
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_relaxed_day_flow"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_lock_window.assert_not_called()

    def test_has_logged_today_exits_before_relaxed_check(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Has logged today exits before relaxed check."""
        create_locker_relaxed_day(mock_tk, tmp_path, has_logged=True)
        mock_sys_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# _check_non_verify_exits: Fri-Mon weekly minimum branch
# ---------------------------------------------------------------------------


class TestWeeklyMinimumBranch:
    """WeeklyMinimumBranch."""

    def test_weekly_minimum_met_exits(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Weekly minimum met exits."""
        with patch(
            "screen_locker._startup_checks.has_weekly_minimum",
            return_value=True,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_called_once_with(0)

    def test_weekly_minimum_not_met_shows_full_lock(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        # create_locker already stubs _start_phone_check; just verify no exit
        # and _relaxed_day_mode stays False (full lock path taken).
        """Weekly minimum not met shows full lock."""
        with patch(
            "screen_locker._startup_checks.has_weekly_minimum",
            return_value=False,
        ):
            locker = create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_not_called()
        assert locker._relaxed_day_mode is False

    def test_weekly_minimum_not_checked_on_relaxed_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Weekly minimum not checked on relaxed day."""
        with patch(
            "screen_locker._startup_checks.has_weekly_minimum",
        ) as mock_weekly:
            create_locker_relaxed_day(mock_tk, tmp_path)

        mock_weekly.assert_not_called()

    def test_has_logged_exits_before_weekly_check(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Has logged exits before weekly check."""
        with patch(
            "screen_locker._startup_checks.has_weekly_minimum",
        ) as mock_weekly:
            create_locker(mock_tk, tmp_path, has_logged=True)

        mock_weekly.assert_not_called()


# ---------------------------------------------------------------------------
# Relaxed-day UI flow methods
# ---------------------------------------------------------------------------
