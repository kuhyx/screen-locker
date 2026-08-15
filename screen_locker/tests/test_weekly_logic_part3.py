"""Tests for _check_today_state_exits and scheduled-skip branches."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._temperature import TemperatureCheck
from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestHeatSkipBranch:
    """HeatSkipBranch."""

    def test_not_too_hot_no_dialog_shown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Not too hot no dialog shown."""
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=20.0, timed_out=False),
            ) as mock_hot,
            patch.object(ScreenLocker, "_show_heat_skip_dialog") as mock_dialog,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_hot.assert_called_once()
        mock_dialog.assert_not_called()
        mock_sys_exit.assert_not_called()

    def test_too_hot_and_user_confirms_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Too hot and user confirms skip."""
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=35.0, timed_out=False),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog", return_value=True),
            patch.object(ScreenLocker, "_save_heat_skip_log") as mock_save,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_save.assert_called_once_with(35.0)
        mock_sys_exit.assert_called_once_with(0)

    def test_too_hot_but_user_declines_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Too hot but user declines skip."""
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=35.0, timed_out=False),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog", return_value=False),
            patch.object(ScreenLocker, "_save_heat_skip_log") as mock_save,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_save.assert_not_called()
        mock_sys_exit.assert_not_called()

    def test_fetch_timed_out_defaults_to_lock_no_dialog(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A timed-out temperature check must fail closed, not skip the lock."""
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=None, timed_out=True),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog") as mock_dialog,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_dialog.assert_not_called()
        mock_sys_exit.assert_not_called()

    def test_fetch_failed_defaults_to_lock_no_dialog(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A failed (non-timeout) temperature check must also fail closed."""
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=None, timed_out=False),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog") as mock_dialog,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_dialog.assert_not_called()
        mock_sys_exit.assert_not_called()
