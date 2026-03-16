"""Tests for UI transitions, timer logic, and workout detail screens."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker.screen_lock import (
    SUBMIT_DELAY_DEMO,
    SUBMIT_DELAY_PRODUCTION,
)
from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

_TK_TCLERROR = tk.TclError


class TestUITransitions:
    """Tests for UI state transitions."""

    def test_clear_container(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test clear_container destroys all child widgets."""
        locker = create_locker(mock_tk, tmp_path)

        # Set up mock children
        mock_child1 = MagicMock()
        mock_child2 = MagicMock()
        locker.container.winfo_children.return_value = [  # type: ignore[attr-defined]
            mock_child1,
            mock_child2,
        ]

        locker.clear_container()

        mock_child1.destroy.assert_called_once()
        mock_child2.destroy.assert_called_once()

    def test_unlock_screen_saves_and_schedules_close(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen saves log and schedules close."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}

        locker.unlock_screen()

        # Check that after() was called to schedule close
        locker.root.after.assert_called()  # type: ignore[attr-defined]

    def test_lockout_starts_countdown(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test lockout initializes countdown timer."""
        locker = create_locker(mock_tk, tmp_path)

        locker.lockout()

        # lockout() sets remaining_time to lockout_time (10 in demo mode)
        # then calls update_lockout_countdown() which decrements it by 1
        assert locker.remaining_time == 9  # 10 - 1 after first update

    def test_close_destroys_root_and_exits(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test close destroys root window and exits."""
        locker = create_locker(mock_tk, tmp_path)

        locker.close()

        locker.root.destroy.assert_called_once()  # type: ignore[attr-defined]
        mock_sys_exit.assert_called_with(0)


class TestTimerLogic:
    """Tests for timer countdown logic."""

    def test_update_lockout_countdown_decrements(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test countdown decrements remaining time."""
        locker = create_locker(mock_tk, tmp_path)
        locker.remaining_time = 5
        locker.countdown_label = MagicMock()

        locker.update_lockout_countdown()

        assert locker.remaining_time == 4
        locker.root.after.assert_called_with(  # type: ignore[attr-defined]
            1000, locker.update_lockout_countdown
        )

    def test_update_lockout_countdown_at_zero(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test countdown at zero returns to workout question."""
        locker = create_locker(mock_tk, tmp_path)
        locker.remaining_time = 0
        locker.countdown_label = MagicMock()
        locker.ask_workout_done = MagicMock()  # type: ignore[method-assign]

        locker.update_lockout_countdown()

        locker.ask_workout_done.assert_called_once()

    def test_update_submit_timer_countdown(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test submit timer counts down."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 5
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        locker.entries_to_check = []

        locker.update_submit_timer()

        assert locker.submit_unlock_time == 4
        locker.root.after.assert_called()  # type: ignore[attr-defined]

    def test_update_submit_timer_enables_when_filled(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test submit enabled when timer done and entries filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 0
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = "some value"
        locker.entries_to_check = [mock_entry]
        locker.submit_command = MagicMock()

        locker.update_submit_timer()

        locker.submit_btn.config.assert_called()

    def test_update_submit_timer_waits_for_entries(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test submit waits when entries not filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 0
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = ""  # Empty entry
        locker.entries_to_check = [mock_entry]

        locker.update_submit_timer()

        locker.root.after.assert_called_with(  # type: ignore[attr-defined]
            1000, locker.check_entries_filled
        )

    def test_update_submit_timer_handles_tcl_error(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test timer handles TclError when widgets destroyed."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 5
        locker.timer_label = MagicMock()
        locker.timer_label.config.side_effect = _TK_TCLERROR("widget destroyed")

        # Should not raise
        locker.update_submit_timer()

    def test_check_entries_filled_enables_submit(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test check_entries_filled enables submit when all filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = "value"
        locker.entries_to_check = [mock_entry]
        locker.submit_command = MagicMock()

        locker.check_entries_filled()

        locker.submit_btn.config.assert_called()

    def test_check_entries_filled_continues_waiting(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test check_entries_filled continues waiting when not filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = ""
        locker.entries_to_check = [mock_entry]

        locker.check_entries_filled()

        locker.root.after.assert_called_with(  # type: ignore[attr-defined]
            1000, locker.check_entries_filled
        )

    def test_check_entries_filled_handles_tcl_error(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test check_entries_filled handles TclError."""
        locker = create_locker(mock_tk, tmp_path)
        locker.timer_label = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.side_effect = _TK_TCLERROR("widget destroyed")
        locker.entries_to_check = [mock_entry]

        # Should not raise
        locker.check_entries_filled()


class TestAskWorkoutType:
    """Tests for ask_workout_type method."""

    def test_ask_workout_type_creates_buttons(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_workout_type creates running and strength buttons."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]

        locker.ask_workout_type()

        locker.clear_container.assert_called_once()
        # Verify Label and Button were called
        mock_tk.Label.assert_called()
        mock_tk.Button.assert_called()


class TestAskRunningDetails:
    """Tests for ask_running_details method."""

    def test_ask_running_details_sets_workout_type(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_running_details sets workout type to running."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_running_details()

        assert locker.workout_data["type"] == "running"
        locker.clear_container.assert_called_once()

    def test_ask_running_details_creates_entry_fields(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_running_details creates entry fields."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_running_details()

        # Verify Entry fields were created
        mock_tk.Entry.assert_called()
        assert hasattr(locker, "distance_entry")
        assert hasattr(locker, "time_entry")
        assert hasattr(locker, "pace_entry")

    def test_ask_running_details_sets_timer(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_running_details initializes submit timer."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_running_details()

        assert locker.submit_unlock_time == SUBMIT_DELAY_DEMO
        locker.update_submit_timer.assert_called_once()


class TestAskStrengthDetails:
    """Tests for ask_strength_details method."""

    def test_ask_strength_details_sets_workout_type(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_strength_details sets workout type to strength."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        assert locker.workout_data["type"] == "strength"
        locker.clear_container.assert_called_once()

    def test_ask_strength_details_creates_entry_fields(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_strength_details creates entry fields."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        # Verify Entry fields were created
        mock_tk.Entry.assert_called()
        assert hasattr(locker, "exercises_entry")
        assert hasattr(locker, "sets_entry")
        assert hasattr(locker, "reps_entry")
        assert hasattr(locker, "weights_entry")
        assert hasattr(locker, "total_weight_entry")

    def test_ask_strength_details_sets_timer(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_strength_details initializes submit timer."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        assert locker.submit_unlock_time == SUBMIT_DELAY_DEMO
        locker.update_submit_timer.assert_called_once()

    def test_ask_strength_details_production_timer(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test production mode uses longer submit delay."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        assert locker.submit_unlock_time == SUBMIT_DELAY_PRODUCTION


class TestAskWorkoutDone:
    """Tests for ask_workout_done method."""

    def test_ask_workout_done_creates_buttons(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test ask_workout_done creates yes/no buttons."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]

        locker.ask_workout_done()

        locker.clear_container.assert_called_once()
        mock_tk.Label.assert_called()
        mock_tk.Button.assert_called()
