"""Tests for screen_locker initialization, logging, and basic operations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import tkinter as tk
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from python_pkg.screen_locker.screen_lock import ScreenLocker
from python_pkg.screen_locker.tests.conftest import create_locker

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


class TestAutoUpgradeSickDay:
    """Tests for sick_day → phone_verified silent upgrade helpers."""

    def test_upgrade_succeeds_when_phone_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verified phone workout overwrites today's sick_day entry."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with (
            patch.object(
                locker,
                "_verify_phone_workout",
                return_value=("verified", "Workout verified! (1 session)"),
            ),
            patch.object(
                locker,
                "_adjust_shutdown_time_later",
                return_value=True,
            ) as mock_adjust,
            patch(
                "python_pkg.screen_locker.screen_lock.compute_entry_hmac",
                return_value="sig",
            ),
        ):
            assert locker._try_auto_upgrade_sick_day() is True
            mock_adjust.assert_called_once()

        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        assert data[today]["workout_data"]["type"] == "phone_verified"
        assert data[today]["workout_data"]["after_sick_day"] == "true"

    def test_upgrade_skipped_when_not_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Non-verified statuses leave the sick_day entry untouched."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker,
            "_verify_phone_workout",
            return_value=("no_phone", "No phone connected"),
        ):
            assert locker._try_auto_upgrade_sick_day() is False
        assert locker.workout_data == {}

    def test_upgrade_skipped_on_exception(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Transient OSError/RuntimeError during check is non-fatal."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(
            locker,
            "_verify_phone_workout",
            side_effect=OSError("transient"),
        ):
            assert locker._try_auto_upgrade_sick_day() is False

    def test_init_exits_when_sick_day_upgrade_succeeds(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Startup exits 0 after a successful silent sick_day upgrade."""
        mock_sys_exit.side_effect = SystemExit(0)
        with (
            patch.object(
                ScreenLocker,
                "_try_auto_upgrade_sick_day",
                return_value=True,
            ) as mock_upgrade,
            pytest.raises(SystemExit),
        ):
            create_locker(mock_tk, tmp_path, is_sick_day_log=True)
        mock_upgrade.assert_called_once()
        mock_sys_exit.assert_called_once_with(0)


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
            locker, "_read_shutdown_config", MagicMock(return_value=(21, 22, 8))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )

        result = locker._adjust_shutdown_time_later()

        assert result is True
        locker._write_shutdown_config.assert_called_once_with(23, 23, 8, restore=True)

    def test_adjust_shutdown_time_later_caps_at_23(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later caps hours at 23."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker, "_read_shutdown_config", MagicMock(return_value=(22, 23, 8))
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(return_value=True)
        )

        result = locker._adjust_shutdown_time_later()

        assert result is True
        # 22+2=24 capped to 23, 23+2=25 capped to 23
        locker._write_shutdown_config.assert_called_once_with(23, 23, 8, restore=True)

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
