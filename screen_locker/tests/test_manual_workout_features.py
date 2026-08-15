"""Tests for manual-workout integration in _ui_flows.py and screen_lock.py."""
# pylint: disable=protected-access

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _manual_workout, _sick_tracker
from screen_locker._sick_tracker import SickHistory
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


class TestShowRetryAndManualWorkoutBudget:
    """Tests for the "Log Manual Workout" button in _show_retry_and_sick."""

    def test_shows_button_when_budget_available(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Shows button when budget available."""
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
        """Hides button when budget exhausted."""
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
        """Sets workout data and schedules unlock."""
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
        """Returns to phone check."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_start_phone_check", MagicMock())
        locker._on_manual_workout_cancelled()
        locker._start_phone_check.assert_called_once()
