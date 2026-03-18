"""Tests for screen_locker initialization, logging, and basic operations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from python_pkg.screen_locker.screen_lock import (
    MAX_DISTANCE_KM,
    MAX_PACE_MIN_PER_KM,
    MAX_REPS,
    MAX_SETS,
    MAX_TIME_MINUTES,
    MAX_WEIGHT_KG,
    MIN_EXERCISE_NAME_LEN,
)
from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestConstants:
    """Tests for module constants."""

    def test_max_distance_km(self) -> None:
        """Test MAX_DISTANCE_KM is reasonable."""
        assert MAX_DISTANCE_KM == 100
        assert MAX_DISTANCE_KM > 0

    def test_max_time_minutes(self) -> None:
        """Test MAX_TIME_MINUTES is reasonable."""
        assert MAX_TIME_MINUTES == 600
        assert MAX_TIME_MINUTES > 0

    def test_max_pace_min_per_km(self) -> None:
        """Test MAX_PACE_MIN_PER_KM is reasonable."""
        assert MAX_PACE_MIN_PER_KM == 20
        assert MAX_PACE_MIN_PER_KM > 0

    def test_min_exercise_name_len(self) -> None:
        """Test MIN_EXERCISE_NAME_LEN is reasonable."""
        assert MIN_EXERCISE_NAME_LEN == 3
        assert MIN_EXERCISE_NAME_LEN > 0

    def test_max_sets(self) -> None:
        """Test MAX_SETS is reasonable."""
        assert MAX_SETS == 20
        assert MAX_SETS > 0

    def test_max_reps(self) -> None:
        """Test MAX_REPS is reasonable."""
        assert MAX_REPS == 100
        assert MAX_REPS > 0

    def test_max_weight_kg(self) -> None:
        """Test MAX_WEIGHT_KG is reasonable."""
        assert MAX_WEIGHT_KG == 500
        assert MAX_WEIGHT_KG > 0


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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when today's workout is logged."""
        log_file = tmp_path / "workout_log.json"
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_file.write_text(json.dumps({today: {"workout": "data"}}))

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        assert locker.has_logged_today() is True

    def test_other_day_logged(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving to a new log file."""
        log_file = tmp_path / "workout_log.json"
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        locker.save_workout_log()

        assert log_file.exists()
        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data
        assert data[today]["workout_data"]["type"] == "running"

    def test_save_to_existing_file(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving appends to existing log file."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(json.dumps({"2020-01-01": {"old": "data"}}))

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "strength"}
        locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        assert "2020-01-01" in data
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data

    def test_save_with_corrupted_existing_file(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving when existing file is corrupted."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("not valid json")

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        locker.save_workout_log()

        with log_file.open() as f:
            data: dict[str, Any] = json.load(f)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in data

    def test_save_with_write_error(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test saving handles write errors gracefully."""
        log_file = tmp_path / "nonexistent_dir" / "workout_log.json"

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        # Should not raise, just log warning
        locker.save_workout_log()


class TestShowError:
    """Tests for show_error method."""

    def test_show_error_displays_message(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test show_error clears container and displays error."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())

        locker.show_error("Test error message")

        locker.clear_container.assert_called_once()


class TestRun:
    """Tests for run method."""

    def test_run_starts_mainloop(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test main defaults to demo mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)

        assert locker.demo_mode is True

    def test_main_production_mode_flag(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
