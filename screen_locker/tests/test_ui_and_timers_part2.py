"""Tests for handle_sick_day and sick day UI."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker.screen_lock import (
    SICK_LOCKOUT_SECONDS,
)
from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestHandleSickDay:
    """Tests for handle_sick_day method."""

    def test_sets_up_countdown(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test handle_sick_day initializes sick day flow."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())
        object.__setattr__(
            locker, "_sick_mode_used_today", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_adjust_shutdown_time_earlier", MagicMock(return_value=True)
        )
        locker.handle_sick_day()
        locker.clear_container.assert_called_once()
        assert locker.sick_remaining_time == SICK_LOCKOUT_SECONDS - 1


class TestShowSickDayUi:
    """Tests for _show_sick_day_ui method."""

    def test_displays_ui(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test _show_sick_day_ui displays labels."""
        locker = create_locker(mock_tk, tmp_path)
        locker._show_sick_day_ui("Test status", "#00aa00")
        mock_tk.Label.assert_called()
        assert hasattr(locker, "sick_countdown_label")
