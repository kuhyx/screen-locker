"""Tests for sick-day state save/load and config restoration."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestAdjustShutdownTimeBy:
    """Tests for _adjust_shutdown_time_by method (extra-workout bonus)."""

    def test_adjusts_time_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Normal path: reads config, increments both hours, writes back."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1260, 1260, 300))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )
        assert locker._adjust_shutdown_time_by(60) is True
        locker._write_shutdown_config.assert_called_once_with(
            1320, 1320, 300, restore=True
        )

    def test_caps_at_midnight(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Times are capped at 1440 minutes (midnight-safe shutdown)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1380, 1380, 300))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )
        locker._adjust_shutdown_time_by(120)
        locker._write_shutdown_config.assert_called_once_with(
            1440, 1440, 300, restore=True
        )

    def test_returns_false_when_config_is_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_read_shutdown_config returns None → return False immediately."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=None)
        )
        assert locker._adjust_shutdown_time_by(1) is False

    def test_returns_false_on_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """OSError during read is caught; returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=OSError("permission denied")),
        )
        assert locker._adjust_shutdown_time_by(1) is False

    def test_returns_false_on_value_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """ValueError during processing is caught; returns False."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=ValueError("bad value")),
        )
        assert locker._adjust_shutdown_time_by(1) is False
