"""Tests for manual-workout integration in _ui_flows.py and screen_lock.py."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _manual_workout, _sick_tracker
from screen_locker._log_mixin import RecordResult
from screen_locker._sick_tracker import SickHistory
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestShowRetryAndManualWorkoutBudget:
    """Tests for the "Log Manual Workout" button in _show_retry_and_sick."""

    def test_shows_button_when_budget_available(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(_sick_tracker, "load_history", return_value=SickHistory()),
            patch.object(_manual_workout, "is_budget_exhausted", return_value=False),
        ):
            locker._show_retry_and_sick("nope")
        button_texts = {c.kwargs.get("text") for c in mock_tk.Button.call_args_list}
        assert "Log Manual Workout" in button_texts

    def test_hides_button_when_budget_exhausted(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(_sick_tracker, "load_history", return_value=SickHistory()),
            patch.object(_manual_workout, "is_budget_exhausted", return_value=True),
        ):
            locker._show_retry_and_sick("nope")
        button_texts: set[str] = set()
        for call in mock_tk.Button.call_args_list:
            button_texts.add(call.kwargs.get("text", ""))
        assert "Log Manual Workout" not in button_texts
        text_calls = [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]
        assert any("Manual-workout budget exhausted" in t for t in text_calls)


class TestOnManualWorkoutSaved:
    """Tests for UIFlowsMixin._on_manual_workout_saved."""

    def test_sets_workout_data_and_schedules_unlock(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "unlock_screen", MagicMock())
        object.__setattr__(locker.root, "after", MagicMock())
        entry = {"type": "manual_workout", "source": "table tennis at Solec"}

        locker._on_manual_workout_saved(entry)

        assert locker.workout_data == entry
        locker.unlock_screen.assert_not_called()
        locker.root.after.assert_called_once_with(1500, locker.unlock_screen)


class TestOnManualWorkoutCancelled:
    """Tests for UIFlowsMixin._on_manual_workout_cancelled."""

    def test_returns_to_phone_check(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_start_phone_check", MagicMock())
        locker._on_manual_workout_cancelled()
        locker._start_phone_check.assert_called_once()


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
