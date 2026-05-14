"""Tests for sick-day countdown flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker._sick_tracker import SickHistory
from python_pkg.screen_locker.screen_lock import (
    SICK_LOCKOUT_SECONDS,
)
from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestProceedToSickCountdown:
    """Tests for _proceed_to_sick_countdown."""

    def test_sets_up_countdown(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Countdown initialises with computed escalated value."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())
        object.__setattr__(
            locker, "_sick_mode_used_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_earlier", MagicMock(return_value=True)
        )
        locker._sick_history_cache = SickHistory()
        locker._proceed_to_sick_countdown()
        locker.clear_container.assert_called_once()
        # First tick has decremented once -> base - 1
        assert locker.sick_remaining_time == SICK_LOCKOUT_SECONDS - 1


class TestShowSickDayUi:
    """Tests for _show_sick_day_ui method."""

    def test_displays_ui(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """_show_sick_day_ui displays labels with explicit countdown."""
        locker = create_locker(mock_tk, tmp_path)
        locker._show_sick_day_ui("Test status", "#00aa00", 120)
        mock_tk.Label.assert_called()
        assert hasattr(locker, "sick_countdown_label")
