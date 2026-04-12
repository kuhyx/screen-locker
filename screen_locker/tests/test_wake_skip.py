"""Tests for wake alarm skip integration in screen_lock.py."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestWakeSkipIntegration:
    """Tests for workout skip via wake alarm in screen locker init."""

    def test_exits_when_wake_skip_active(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Screen locker exits if wake alarm granted workout skip today."""
        with patch(
            "python_pkg.screen_locker.screen_lock.has_workout_skip_today",
            return_value=True,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_called_once_with(0)

    def test_does_not_exit_when_no_wake_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Screen locker proceeds normally if no wake skip active."""
        with patch(
            "python_pkg.screen_locker.screen_lock.has_workout_skip_today",
            return_value=False,
        ):
            locker = create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_not_called()
        assert locker is not None

    def test_logged_today_takes_precedence(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """has_logged_today exits before wake skip is even checked."""
        with patch(
            "python_pkg.screen_locker.screen_lock.has_workout_skip_today",
            return_value=True,
        ):
            create_locker(mock_tk, tmp_path, has_logged=True)

        # Exits because has_logged_today, not because of wake skip
        mock_sys_exit.assert_called_once_with(0)

    def test_verify_only_mode_ignores_wake_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """verify_only mode checks sick day log, not wake skip."""
        with patch(
            "python_pkg.screen_locker.screen_lock.has_workout_skip_today",
            return_value=True,
        ):
            create_locker(
                mock_tk,
                tmp_path,
                verify_only=True,
                is_sick_day_log=True,
            )

        # In verify_only mode, exits don't happen from wake skip path
        mock_sys_exit.assert_not_called()
