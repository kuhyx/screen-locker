"""Tests for manual-workout integration in _ui_flows.py and screen_lock.py."""
# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _manual_workout, _sick_tracker
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


def _write_today_entry(log_file: Path, today: str, entry_type: str) -> None:
    """Write a single workout_log.json entry for *today*."""
    log_file.write_text(
        json.dumps(
            {
                today: {
                    "timestamp": f"{today}T08:00:00+00:00",
                    "workout_data": {"type": entry_type},
                }
            }
        )
    )


class TestWasAlreadyCountedToday:
    """Tests for ScreenLocker._was_already_counted_today."""

    def test_false_when_no_log_file(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        assert locker._was_already_counted_today() is False

    def test_false_when_todays_entry_missing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file.write_text(
            json.dumps({"2020-01-01": {"workout_data": {"type": "phone_verified"}}})
        )
        assert locker._was_already_counted_today() is False

    def test_true_when_todays_entry_is_counted_type(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "screen_locker._workout_credit.datetime",
        ) as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-07-05"
            _write_today_entry(locker.log_file, "2026-07-05", "manual_workout")
            assert locker._was_already_counted_today() is True

    def test_false_when_todays_entry_is_noncounted_type(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch("screen_locker._workout_credit.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-07-05"
            _write_today_entry(locker.log_file, "2026-07-05", "sick_day")
            assert locker._was_already_counted_today() is False


class TestApplyWorkoutCredit:
    """Tests for ScreenLocker._apply_workout_credit."""

    def test_skips_credit_when_already_counted_today(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "manual_workout"}
        object.__setattr__(
            locker, "_was_already_counted_today", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=0)
        )
        object.__setattr__(locker, "save_workout_log", MagicMock())

        result = locker._apply_workout_credit()

        assert result.already_counted_today is True
        assert result.shutdown_adjusted is False
        assert result.new_debt is None
        assert result.extra_bonus_delta == 0
        locker._try_adjust_shutdown_for_workout.assert_not_called()
        locker._clear_debt_on_verified_workout.assert_not_called()
        locker.save_workout_log.assert_called_once()  # log entry still saved

    def test_applies_credit_when_not_already_counted(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "manual_workout"}
        object.__setattr__(
            locker, "_was_already_counted_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=True)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=2)
        )
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(21, 21, 5))
        )

        result = locker._apply_workout_credit()

        assert result.already_counted_today is False
        assert result.shutdown_adjusted is True
        assert result.new_debt == 2
        assert result.extra_bonus_delta == 0

    def test_extra_bonus_applied_above_weekly_minimum(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "manual_workout"}
        object.__setattr__(
            locker, "_was_already_counted_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=[(21, 21, 5), (22, 22, 5)]),
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_by", MagicMock(return_value=True)
        )
        with patch(
            "screen_locker._workout_credit.count_weekly_workouts", return_value=5
        ):
            result = locker._apply_workout_credit()

        assert result.weekly_count == 5
        assert result.extra_bonus_delta == 1

    def test_skips_save_for_sick_day_type(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"type": "sick_day"}
        object.__setattr__(
            locker, "_was_already_counted_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )
        object.__setattr__(locker, "save_workout_log", MagicMock())

        locker._apply_workout_credit()

        locker.save_workout_log.assert_not_called()
