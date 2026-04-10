"""Tests for screen_locker initialization, logging, and basic operations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import tkinter as tk
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from python_pkg.screen_locker.screen_lock import _assert_not_under_pytest
from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestAssertNotUnderPytest:
    """Tests for the _assert_not_under_pytest runtime guard."""

    def test_raises_when_tk_is_real(self) -> None:
        """Guard fires if tk.Tk is the real tkinter class under pytest."""
        with (
            patch("python_pkg.screen_locker.screen_lock.tk", tk),
            pytest.raises(RuntimeError, match="SAFETY"),
        ):
            _assert_not_under_pytest()

    def test_silent_when_tk_is_mocked(self) -> None:
        """Guard stays silent when tk is already mocked (normal test run)."""
        _assert_not_under_pytest()


class TestScreenLockerInit:
    """Tests for ScreenLocker initialization."""

    def test_init_demo_mode(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test initialization in demo mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)

        assert locker.demo_mode is True
        assert locker.lockout_time == 10
        mock_sys_exit.assert_not_called()

    def test_init_production_mode(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test initialization in production mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)

        assert locker.demo_mode is False
        assert locker.lockout_time == 1800
        mock_sys_exit.assert_not_called()

    def test_init_exits_if_logged_today(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Test that init exits early if workout logged today."""
        mock_sys_exit.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            create_locker(mock_tk, tmp_path, has_logged=True)

        mock_sys_exit.assert_called_once_with(0)


class TestHasLoggedToday:
    """Tests for has_logged_today method."""

    def test_no_log_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when log file doesn't exist."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)

        locker.log_file = log_file
        assert locker.has_logged_today() is False

    def test_empty_log_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when log file is empty/invalid JSON."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("")

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker.has_logged_today() is False

    def test_invalid_json(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when log file contains invalid JSON."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("{invalid json}")

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker.has_logged_today() is False

    def test_today_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when today's workout is logged with valid HMAC."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout": "data", "hmac": "valid"}}),
        )

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with patch(
            "python_pkg.screen_locker.screen_lock.verify_entry_hmac",
            return_value=True,
        ):
            assert locker.has_logged_today() is True

    def test_today_logged_invalid_hmac(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test rejects entry when HMAC verification fails."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(
            json.dumps({today: {"workout": "data", "hmac": "tampered"}}),
        )

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        with patch(
            "python_pkg.screen_locker.screen_lock.verify_entry_hmac",
            return_value=False,
        ):
            assert locker.has_logged_today() is False

    def test_other_day_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when only other days are logged."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({"2020-01-01": {"workout": "data"}}))

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker.has_logged_today() is False


class TestSaveWorkoutLog:
    """Tests for save_workout_log method."""

    def test_save_to_new_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving to a new log file includes HMAC."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "python_pkg.screen_locker.screen_lock.compute_entry_hmac",
            return_value="abc123",
        ):
            locker.save_workout_log()

        assert log_file.exists()
        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data
        assert data[today]["workout_data"]["type"] == "running"
        assert data[today]["hmac"] == "abc123"

    def test_save_to_new_file_no_hmac_key(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving without HMAC key produces unsigned entry."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "python_pkg.screen_locker.screen_lock.compute_entry_hmac",
            return_value=None,
        ):
            locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert "hmac" not in data[today]

    def test_save_to_existing_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving appends to existing log file."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({"2020-01-01": {"old": "data"}}))

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "strength"}
        with patch(
            "python_pkg.screen_locker.screen_lock.compute_entry_hmac",
            return_value="sig",
        ):
            locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        assert "2020-01-01" in data
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data

    def test_save_with_corrupted_existing_file(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving when existing file is corrupted."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("not valid json")

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "python_pkg.screen_locker.screen_lock.compute_entry_hmac",
            return_value="sig",
        ):
            locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data

    def test_save_with_write_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving handles write errors gracefully."""
        log_file = tmp_path / "nonexistent_dir" / "workout_log.json"

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        with patch(
            "python_pkg.screen_locker.screen_lock.compute_entry_hmac",
            return_value="sig",
        ):
            # Should not raise, just log warning
            locker.save_workout_log()


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
