"""More workout-credit cases: bonuses, unreadable config, sick days.

Split out of test_manual_workout_features_part2.py for the 250-line cap.
"""
# pylint: disable=protected-access

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker._log_mixin import RecordResult
from screen_locker.tests.conftest import create_locker

# The Dart mirror of the budget caps; read at test time so drift on
# EITHER side fails, not just a local edit to the Python constants.
DART_MANUAL_WORKOUT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "stronglift_replacement"
    / "workout_app"
    / "lib"
    / "models"
    / "manual_workout.dart"
)

if TYPE_CHECKING:
    from pathlib import Path


class TestApplyWorkoutCredit:
    """More _apply_workout_credit cases under the multi-per-day rule."""

    def test_additional_workout_unreadable_shutdown_config_earns_no_bonus(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Additional same-day workout, but the shutdown config can't be read
        (old_cfg is None) → the +1h branch is entered but bails out before
        ever attempting the adjustment."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "phone_verified"}
        prior = [{"workout_data": {"type": "phone_verified"}}]
        object.__setattr__(
            locker,
            "save_workout_log",
            MagicMock(return_value=RecordResult(appended=True, prior_entries=prior)),
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=None)
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_by", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )

        result = locker._apply_workout_credit()

        assert result.shutdown_adjusted is False
        assert result.extra_bonus_delta == 0
        locker._try_adjust_shutdown_for_workout.assert_not_called()
        locker._adjust_shutdown_time_by.assert_not_called()

    def test_additional_workout_of_uncounted_type_earns_nothing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A workout whose type isn't in COUNTED_WORKOUT_TYPES (e.g.
        ``early_bird``) and isn't the first counted entry of the day →
        neither the base push nor the +1h branch fires; the shutdown config
        is never even consulted."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "early_bird"}
        prior = [{"workout_data": {"type": "phone_verified"}}]
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(21, 21, 5))
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_by", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )

        result = locker._apply_credit_for_written_entry(prior)

        assert result.shutdown_adjusted is False
        assert result.extra_bonus_delta == 0
        locker._try_adjust_shutdown_for_workout.assert_not_called()
        locker._read_shutdown_config.assert_not_called()
        locker._adjust_shutdown_time_by.assert_not_called()

    def test_skips_save_for_sick_day_type(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Skips save for sick day type."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "sick_day"}
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )
        object.__setattr__(locker, "save_workout_log", MagicMock())

        result = locker._apply_workout_credit()

        assert result.already_counted_today is False
        assert result.shutdown_adjusted is False
        locker.save_workout_log.assert_not_called()
