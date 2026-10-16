"""Tests for screen_locker initialization, logging, and basic operations."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestRun:
    """Tests for run method."""

    def test_run_starts_mainloop(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test run starts the tkinter mainloop."""
        locker = create_locker(mock_tk, tmp_path)

        locker.run()

        locker.root.mainloop.assert_called_once()


class TestSickDayStandsDown:
    """A sick day (sickdays pool) skips the lock; nothing is upgraded or logged."""

    def test_init_exits_on_a_sick_day_without_touching_the_phone(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Startup exits 0 and never runs a phone or RunnerUp check."""
        mock_sys_exit.side_effect = SystemExit(0)
        with (
            patch.object(ScreenLocker, "_verify_phone_workout") as phone,
            patch.object(ScreenLocker, "_verify_runnerup_workout") as runnerup,
            patch("screen_locker._auto_upgrade.record_decision") as record,
            pytest.raises(SystemExit),
        ):
            create_locker(mock_tk, tmp_path, is_sick_day_log=True)
        mock_sys_exit.assert_called_once_with(0)
        phone.assert_not_called()
        runnerup.assert_not_called()
        assert record.call_args.args[0].reason == "sick_day"


class TestMainEntry:
    """Tests for main entry point."""

    def test_main_demo_mode_default(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test main defaults to demo mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)

        assert locker.demo_mode is True

    def test_main_production_mode_flag(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test main with --production flag."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)

        assert locker.demo_mode is False


@pytest.mark.usefixtures("pre_ladder")
class TestAdjustShutdownTimeLater:
    """Tests for _adjust_shutdown_time_later method."""

    def test_adjust_shutdown_time_later_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later adds hours successfully."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1260, 1320, 480))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )

        result = locker._adjust_shutdown_time_later()

        assert result is True
        locker._write_shutdown_config.assert_called_once_with(
            1380, 1380, 480, restore=True
        )

    def test_adjust_shutdown_time_later_caps_at_23(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later caps hours at 23."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(1320, 1380, 480))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )

        result = locker._adjust_shutdown_time_later()

        assert result is True
        # 22+2=24 capped to 23, 23+2=25 capped to 23
        locker._write_shutdown_config.assert_called_once_with(
            1380, 1380, 480, restore=True
        )

    def test_adjust_shutdown_time_later_no_config(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later returns False if config missing."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=None)
        )

        result = locker._adjust_shutdown_time_later()

        assert result is False

    def test_adjust_shutdown_time_later_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later handles OSError."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=OSError("permission denied")),
        )

        result = locker._adjust_shutdown_time_later()

        assert result is False


class TestGrabInput:
    """Tests for _grab_input method."""

    def test_production_global_grab_tcl_error(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test production mode falls back when global grab fails."""
        mock_tk.Tk.return_value.grab_set_global.side_effect = tk.TclError("grab failed")
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        assert locker.demo_mode is False
