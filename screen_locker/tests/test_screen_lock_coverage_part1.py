"""Tests targeting remaining screen_lock.py coverage gaps."""

from __future__ import annotations

from datetime import datetime, timezone
import json
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
            patch("screen_locker.screen_lock.reset_to_base_if_new_day"),
            patch(
                "screen_locker.screen_lock.count_weekly_workouts", side_effect=[0, 6]
            ),
            patch(
                "screen_locker.screen_lock.process_week_transition",
                return_value=[],
            ),
            patch("screen_locker.screen_lock.is_relaxed_day", return_value=False),
            patch("screen_locker.screen_lock.has_weekly_minimum", return_value=True),
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
            patch("screen_locker.screen_lock.reset_to_base_if_new_day"),
            # prev=2, new=3 → bonus=max(0,3-max(5,2))=0 → no bonus logger call
            patch(
                "screen_locker.screen_lock.count_weekly_workouts", side_effect=[2, 3]
            ),
            patch(
                "screen_locker.screen_lock.process_week_transition",
                return_value=[],
            ),
            patch("screen_locker.screen_lock.is_relaxed_day", return_value=False),
            patch("screen_locker.screen_lock.has_weekly_minimum", return_value=False),
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
            patch("screen_locker.screen_lock.reset_to_base_if_new_day"),
            patch(
                "screen_locker.screen_lock.process_week_transition",
                return_value=["🎉 +1h shutdown bonus for 5-workout week!"],
            ),
            patch("screen_locker.screen_lock.is_relaxed_day", return_value=False),
            patch("screen_locker.screen_lock.has_weekly_minimum", return_value=True),
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
                "screen_locker.screen_lock.reset_to_base_if_new_day", return_value=True
            ),
            patch(
                "screen_locker.screen_lock.process_week_transition",
                return_value=[],
            ),
            patch(
                "screen_locker.screen_lock.weekly_shutdown_bonus_hours",
                return_value=2,
            ),
            patch("screen_locker.screen_lock.is_relaxed_day", return_value=False),
            patch("screen_locker.screen_lock.has_weekly_minimum", return_value=True),
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
                "screen_locker.screen_lock.reset_to_base_if_new_day", return_value=False
            ),
            patch(
                "screen_locker.screen_lock.process_week_transition",
                return_value=[],
            ),
            patch(
                "screen_locker.screen_lock.weekly_shutdown_bonus_hours",
                return_value=2,
            ),
            patch("screen_locker.screen_lock.is_relaxed_day", return_value=False),
            patch("screen_locker.screen_lock.has_weekly_minimum", return_value=True),
            patch("screen_locker.screen_lock.sys.exit"),
        ):
            locker._check_non_verify_exits()
        locker._adjust_shutdown_time_by.assert_not_called()


class TestTryAutoUpgradeSickDayRunnerUp:
    """Tests for RunnerUp paths in _try_auto_upgrade_sick_day (lines 273-286)."""

    def test_runnerup_exception_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """OSError from _verify_runnerup_workout → returns False (lines 273-275)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(side_effect=OSError("adb fail")),
        )
        assert locker._try_auto_upgrade_sick_day() is False

    def test_runnerup_verified_saves_entry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp returns verified → saves runnerup_verified entry (lines 281-286)."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {}
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("verified", "Running: 6 km in 40 min")),
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )
        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None):
            result = locker._try_auto_upgrade_sick_day()

        assert result is True
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        data = json.loads(log_file.read_text())
        assert data[today][0]["workout_data"]["type"] == "runnerup_verified"
        assert data[today][0]["workout_data"]["after_sick_day"] == "true"

    def test_runnerup_not_verified_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp not verified → returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("not_verified", "no run")),
        )
        assert locker._try_auto_upgrade_sick_day() is False


class TestTryAutoUpgradeEarlyBirdRunnerUp:
    """Tests for RunnerUp paths in screen_lock.py _try_auto_upgrade_early_bird (305-318)."""

    def test_runnerup_exception_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RuntimeError from _verify_runnerup_workout → returns False (lines 305-307)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(side_effect=RuntimeError("adb gone")),
        )
        assert locker._try_auto_upgrade_early_bird() is False

    def test_runnerup_verified_saves_entry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp returns verified → saves runnerup_verified entry (lines 313-318)."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {}
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("verified", "Running: 6 km in 40 min")),
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )
        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None):
            result = locker._try_auto_upgrade_early_bird()

        assert result is True
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        data = json.loads(log_file.read_text())
        assert data[today][0]["workout_data"]["type"] == "runnerup_verified"
        assert data[today][0]["workout_data"]["after_early_bird"] == "true"

    def test_runnerup_not_verified_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RunnerUp not verified → returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(return_value=("no_phone", "no phone")),
        )
        object.__setattr__(
            locker,
            "_verify_runnerup_workout",
            MagicMock(return_value=("not_verified", "no run")),
        )
        assert locker._try_auto_upgrade_early_bird() is False


class TestSyncNow:
    """Tests for sync_now, the public entry point behind ``--sync-only``."""

    def test_runs_one_full_sync_pass(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The timer unit's entry point must actually push and ingest.

        ``workout-sync.timer`` calls this headlessly; if it stopped delegating,
        the timer would run and silently sync nothing.
        """
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker.screen_lock.pull_all_manual_records",
                return_value=[("manual:x", {})],
            ),
            patch("screen_locker.screen_lock.push_pc_workouts") as push,
            patch(
                "screen_locker.screen_lock.ingest_manual_records",
                return_value=["manual:x"],
            ) as ingest,
        ):
            locker.sync_now()
        push.assert_called_once()
        ingest.assert_called_once()
