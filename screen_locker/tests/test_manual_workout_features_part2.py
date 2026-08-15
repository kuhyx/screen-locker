"""Tests for manual-workout integration in _ui_flows.py and screen_lock.py."""
# pylint: disable=protected-access

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

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
    """Tests for ScreenLocker._apply_workout_credit under the multi-per-day rule.

    Credit is now driven by the :class:`RecordResult` the write chokepoint
    returns (``appended`` + ``prior_entries``), not a separate
    ``_was_already_counted_today`` probe (removed).
    """

    def test_skips_credit_when_duplicate_already_logged_today(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """save_workout_log reports a duplicate (appended=False) → no new credit."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "manual_workout"}
        object.__setattr__(
            locker,
            "save_workout_log",
            MagicMock(return_value=RecordResult(appended=False, prior_entries=[])),
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=0)
        )

        result = locker._apply_workout_credit()

        assert result.already_counted_today is True
        assert result.shutdown_adjusted is False
        assert result.new_debt is None
        assert result.extra_bonus_delta == 0
        locker._try_adjust_shutdown_for_workout.assert_not_called()
        locker._clear_debt_on_verified_workout.assert_not_called()
        locker.save_workout_log.assert_called_once()  # log entry write attempted

    def test_first_workout_of_day_gets_base_shutdown_push(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """First counted workout of the day (empty prior_entries) → base +2h push."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "manual_workout"}
        object.__setattr__(
            locker,
            "save_workout_log",
            MagicMock(return_value=RecordResult(appended=True, prior_entries=[])),
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=2)
        )

        result = locker._apply_workout_credit()

        assert result.already_counted_today is False
        assert result.shutdown_adjusted is True
        assert result.new_debt == 2
        assert result.extra_bonus_delta == 0
        locker._try_adjust_shutdown_for_workout.assert_called_once()

    def test_additional_manual_workout_earns_plus_one_hour(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A second manual workout on a day that already counted → +1h extra.

        Manual workouts now stack intra-day shutdown credit exactly like
        verified ones — the rate budget (not this stacking rule) is the sole
        limiter on manual workouts. Mirrors
        ``test_additional_verified_workout_earns_plus_one_hour``.
        """
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "manual_workout"}
        prior = [{"workout_data": {"type": "manual_workout"}}]
        object.__setattr__(
            locker,
            "save_workout_log",
            MagicMock(return_value=RecordResult(appended=True, prior_entries=prior)),
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=[(21, 21, 5), (22, 22, 5)]),
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_by", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )
        with patch(
            "screen_locker._workout_credit.count_weekly_workouts", return_value=5
        ):
            result = locker._apply_workout_credit()

        assert result.weekly_count == 5
        assert result.shutdown_adjusted is False
        assert result.extra_bonus_delta == 1
        locker._try_adjust_shutdown_for_workout.assert_not_called()
        locker._adjust_shutdown_time_by.assert_called_once_with(1)

    def test_additional_verified_workout_earns_plus_one_hour(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """An additional same-day VERIFIED workout earns the +1h extra bonus.

        prior_entries already holds a counted workout, so this isn't the first
        of the day; because the new type is verified it takes the +1h branch,
        and extra_bonus_delta reflects the shutdown-config hour delta.
        """
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
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=[(21, 21, 5), (22, 22, 5)]),
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_by", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )
        with patch(
            "screen_locker._workout_credit.count_weekly_workouts", return_value=5
        ):
            result = locker._apply_workout_credit()

        assert result.weekly_count == 5
        assert result.shutdown_adjusted is False
        assert result.extra_bonus_delta == 1
        locker._try_adjust_shutdown_for_workout.assert_not_called()
        locker._adjust_shutdown_time_by.assert_called_once_with(1)
