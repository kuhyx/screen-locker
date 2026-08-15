"""Tests targeting remaining screen_lock.py coverage gaps."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestCheckNonVerifyExitsExtras:
    """Tests for _check_non_verify_exits coverage gaps (lines 228, 233, 251-254)."""

    def test_logs_auto_filled_runnerup_entries(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_scan_and_fill_week_runnerup > 0 + bonus > 0 → bonus logger.info (line 188)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_scan_and_fill_week_runnerup",
            MagicMock(return_value=2),
        )
        # Short-circuit _check_today_state_exits so the test is time-independent.
        object.__setattr__(
            locker,
            "_check_today_state_exits",
            MagicMock(return_value=False),
        )
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_by",
            MagicMock(return_value=True),
        )
        with (
            patch("screen_locker._startup_checks.reset_to_base_if_new_day"),
            patch(
                "screen_locker._sync_mixin.count_weekly_workouts", side_effect=[0, 6]
            ),
            patch(
                "screen_locker._startup_checks.process_week_transition",
                return_value=[],
            ),
            patch("screen_locker._startup_checks.is_relaxed_day", return_value=False),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=True
            ),
            patch("screen_locker.screen_lock.sys.exit"),
        ):
            locker._check_non_verify_exits()
        locker._adjust_shutdown_time_by.assert_called_once_with(1)  # bonus = 6-max(5,0)

    def test_auto_fill_no_bonus_when_min_not_exceeded(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """n_filled > 0 but new_count <= min → bonus=0 → branch 187->190 (no bonus log)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_scan_and_fill_week_runnerup",
            MagicMock(return_value=1),
        )
        object.__setattr__(
            locker,
            "_check_today_state_exits",
            MagicMock(return_value=False),
        )
        with (
            patch("screen_locker._startup_checks.reset_to_base_if_new_day"),
            # prev=2, new=3 → bonus=max(0,3-max(5,2))=0 → no bonus logger call
            patch(
                "screen_locker._sync_mixin.count_weekly_workouts", side_effect=[2, 3]
            ),
            patch(
                "screen_locker._startup_checks.process_week_transition",
                return_value=[],
            ),
            patch("screen_locker._startup_checks.is_relaxed_day", return_value=False),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch("screen_locker.screen_lock.sys.exit"),
        ):
            locker._check_non_verify_exits()

    def test_logs_weekly_reward_message(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """process_week_transition returning messages → logger.info at line 233."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_scan_and_fill_week_runnerup",
            MagicMock(return_value=0),
        )
        with (
            patch("screen_locker._startup_checks.reset_to_base_if_new_day"),
            patch(
                "screen_locker._startup_checks.process_week_transition",
                return_value=["🎉 +1h shutdown bonus for 5-workout week!"],
            ),
            patch("screen_locker._startup_checks.is_relaxed_day", return_value=False),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=True
            ),
            patch("screen_locker.screen_lock.sys.exit"),
        ):
            locker._check_non_verify_exits()

    def test_applies_weekly_bonus_on_fresh_day_reset(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """reset_to_base_if_new_day True → weekly shutdown bonus is applied once."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_scan_and_fill_week_runnerup",
            MagicMock(return_value=0),
        )
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_by",
            MagicMock(return_value=True),
        )
        with (
            patch(
                "screen_locker._startup_checks.reset_to_base_if_new_day",
                return_value=True,
            ),
            patch(
                "screen_locker._startup_checks.process_week_transition",
                return_value=[],
            ),
            patch(
                "screen_locker._sync_mixin.weekly_shutdown_bonus_hours",
                return_value=2,
            ),
            patch("screen_locker._startup_checks.is_relaxed_day", return_value=False),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=True
            ),
            patch("screen_locker.screen_lock.sys.exit"),
        ):
            locker._check_non_verify_exits()
        locker._adjust_shutdown_time_by.assert_called_once_with(2)

    def test_no_weekly_bonus_applied_when_not_a_fresh_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """reset_to_base_if_new_day False (same-day restart) → bonus not re-applied."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_scan_and_fill_week_runnerup",
            MagicMock(return_value=0),
        )
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_by",
            MagicMock(return_value=True),
        )
        with (
            patch(
                "screen_locker._startup_checks.reset_to_base_if_new_day",
                return_value=False,
            ),
            patch(
                "screen_locker._startup_checks.process_week_transition",
                return_value=[],
            ),
            patch(
                "screen_locker._sync_mixin.weekly_shutdown_bonus_hours",
                return_value=2,
            ),
            patch("screen_locker._startup_checks.is_relaxed_day", return_value=False),
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=True
            ),
            patch("screen_locker.screen_lock.sys.exit"),
        ):
            locker._check_non_verify_exits()
        locker._adjust_shutdown_time_by.assert_not_called()
