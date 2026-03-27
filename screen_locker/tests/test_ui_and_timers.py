"""Tests for UI transitions, timer logic, and sick day screens."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestUITransitions:
    """Tests for UI state transitions."""

    def test_clear_container(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test clear_container destroys all child widgets."""
        locker = create_locker(mock_tk, tmp_path)

        # Set up mock children
        mock_child1 = MagicMock()
        mock_child2 = MagicMock()
        locker.container.winfo_children.return_value = [
            mock_child1,
            mock_child2,
        ]

        locker.clear_container()

        mock_child1.destroy.assert_called_once()
        mock_child2.destroy.assert_called_once()

    def test_unlock_screen_saves_and_schedules_close(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen saves log and schedules close."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "phone_verified"}

        locker.unlock_screen()

        # Check that after() was called to schedule close
        locker.root.after.assert_called()

    def test_lockout_starts_countdown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
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

        locker.root.destroy.assert_called_once()
        mock_sys_exit.assert_called_with(0)


class TestTimerLogic:
    """Tests for timer countdown logic."""

    def test_update_lockout_countdown_decrements(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test countdown decrements remaining time."""
        locker = create_locker(mock_tk, tmp_path)
        locker.remaining_time = 5
        locker.countdown_label = MagicMock()

        locker.update_lockout_countdown()

        assert locker.remaining_time == 4
        locker.root.after.assert_called_with(1000, locker.update_lockout_countdown)

    def test_update_lockout_countdown_at_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test countdown at zero restarts phone check."""
        locker = create_locker(mock_tk, tmp_path)
        locker.remaining_time = 0
        locker.countdown_label = MagicMock()
        object.__setattr__(locker, "_start_phone_check", MagicMock())

        locker.update_lockout_countdown()

        locker._start_phone_check.assert_called_once()


class TestAskIfSick:
    """Tests for ask_if_sick method."""

    def test_ask_if_sick_displays_dialog(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test ask_if_sick shows sick day question."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())
        locker.ask_if_sick()
        locker.clear_container.assert_called_once()
        mock_tk.Label.assert_called()


class TestSickQuestionButtons:
    """Tests for _sick_question_buttons method."""

    def test_creates_buttons(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test _sick_question_buttons creates yes/no buttons."""
        locker = create_locker(mock_tk, tmp_path)
        locker._sick_question_buttons()
        mock_tk.Button.assert_called()


class TestGetSickDayStatus:
    """Tests for _get_sick_day_status method."""

    def test_already_adjusted_today(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test status when sick mode already used today."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_sick_mode_used_today", MagicMock(return_value=True)
        )
        text, color = locker._get_sick_day_status()
        assert "already adjusted" in text
        assert color == "#ffaa00"

    def test_adjustment_success(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test status when shutdown time adjusted successfully."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_sick_mode_used_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_earlier", MagicMock(return_value=True)
        )
        text, color = locker._get_sick_day_status()
        assert "earlier" in text
        assert color == "#00aa00"

    def test_adjustment_failure(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test status when adjustment fails."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_sick_mode_used_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_earlier", MagicMock(return_value=False)
        )
        text, color = locker._get_sick_day_status()
        assert "Could not adjust" in text
        assert color == "#ff4444"


class TestShowRetryAndSick:
    """Tests for _show_retry_and_sick method."""

    def test_displays_buttons(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test _show_retry_and_sick shows retry and sick buttons."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())

        locker._show_retry_and_sick("Test message")

        locker.clear_container.assert_called_once()
        mock_tk.Label.assert_called()
        mock_tk.Button.assert_called()
