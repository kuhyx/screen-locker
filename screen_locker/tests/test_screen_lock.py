"""Comprehensive tests for screen_locker module.

Tests cover:
- ScreenLocker initialization and configuration
- Workout data validation (running and strength)
- Log file operations (reading/writing)
- UI state transitions
- Timer logic
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import tkinter as tk
from typing import TYPE_CHECKING, Any, NamedTuple
from unittest.mock import MagicMock, patch

import pytest

from python_pkg.screen_locker.screen_lock import (
    MAX_DISTANCE_KM,
    MAX_PACE_MIN_PER_KM,
    MAX_REPS,
    MAX_SETS,
    MAX_TIME_MINUTES,
    MAX_WEIGHT_KG,
    MIN_EXERCISE_NAME_LEN,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    STRONGLIFTS_DB_REMOTE,
    SUBMIT_DELAY_DEMO,
    SUBMIT_DELAY_PRODUCTION,
    ScreenLocker,
)

if TYPE_CHECKING:
    from collections.abc import Generator

# Reference tk to avoid import-but-unused error
_TK_TCLERROR = tk.TclError


class RunningData(NamedTuple):
    """Running workout data for tests."""

    distance: str
    time_mins: str
    pace: str


class StrengthData(NamedTuple):
    """Strength workout data for tests."""

    exercises: str
    sets: str
    reps: str
    weights: str
    total_weight: str


@pytest.fixture
def mock_tk() -> Generator[MagicMock]:
    """Mock tkinter module for testing without display."""
    with patch("python_pkg.screen_locker.screen_lock.tk") as mock:
        # Set up Tk root mock
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock.Tk.return_value = mock_root

        # Set up Frame mock
        mock_frame = MagicMock()
        mock_frame.winfo_children.return_value = []
        mock.Frame.return_value = mock_frame

        # Set up TclError as actual exception class
        mock.TclError = _TK_TCLERROR

        yield mock


@pytest.fixture
def mock_sys_exit() -> Generator[MagicMock]:
    """Mock sys.exit to prevent test termination."""
    with patch("python_pkg.screen_locker.screen_lock.sys.exit") as mock:
        yield mock


@pytest.fixture
def temp_log_file(tmp_path: Path) -> Path:
    """Create a temporary log file path."""
    return tmp_path / "workout_log.json"


def create_locker(
    mock_tk: MagicMock,  # noqa: ARG001
    tmp_path: Path,
    *,
    demo_mode: bool = True,
    has_logged: bool = False,
) -> ScreenLocker:
    """Create a ScreenLocker instance for testing."""
    with (
        patch.object(Path, "resolve", return_value=tmp_path),
        patch.object(ScreenLocker, "has_logged_today", return_value=has_logged),
        patch.object(ScreenLocker, "_start_phone_check"),
    ):
        return ScreenLocker(demo_mode=demo_mode)


def setup_running_entries(locker: ScreenLocker, data: RunningData) -> None:
    """Set up mock running entry widgets."""
    locker.distance_entry = MagicMock()
    locker.distance_entry.get.return_value = data.distance
    locker.time_entry = MagicMock()
    locker.time_entry.get.return_value = data.time_mins
    locker.pace_entry = MagicMock()
    locker.pace_entry.get.return_value = data.pace


def setup_strength_entries(locker: ScreenLocker, data: StrengthData) -> None:
    """Set up mock strength entry widgets."""
    locker.exercises_entry = MagicMock()
    locker.exercises_entry.get.return_value = data.exercises
    locker.sets_entry = MagicMock()
    locker.sets_entry.get.return_value = data.sets
    locker.reps_entry = MagicMock()
    locker.reps_entry.get.return_value = data.reps
    locker.weights_entry = MagicMock()
    locker.weights_entry.get.return_value = data.weights
    locker.total_weight_entry = MagicMock()
    locker.total_weight_entry.get.return_value = data.total_weight


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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
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
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test saving handles write errors gracefully."""
        log_file = tmp_path / "nonexistent_dir" / "workout_log.json"

        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "running"}
        # Should not raise, just log warning
        locker.save_workout_log()


class TestVerifyRunningData:
    """Tests for verify_running_data method."""

    def test_valid_running_data(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test valid running data triggers unlock attempt."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("5", "25", "5"))
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}
        locker._attempt_unlock = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker._attempt_unlock.assert_called_once()

    def test_invalid_distance_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test zero distance is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("0", "25", "5"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "Distance" in locker.show_error.call_args[0][0]

    def test_invalid_distance_too_high(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test distance over max is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("150", "600", "4"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "Distance" in locker.show_error.call_args[0][0]

    def test_invalid_time_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test zero time is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("5", "0", "5"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "Time" in locker.show_error.call_args[0][0]

    def test_invalid_time_too_high(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test time over max is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("5", "700", "5"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "Time" in locker.show_error.call_args[0][0]

    def test_invalid_pace_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test zero pace is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("5", "25", "0"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "Pace" in locker.show_error.call_args[0][0]

    def test_invalid_pace_too_high(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test pace over max is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("5", "25", "25"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "Pace" in locker.show_error.call_args[0][0]

    def test_pace_mismatch(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test pace mismatch is rejected."""
        # 5km in 25 min should be 5 min/km, but we say 10 min/km
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("5", "25", "10"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "Pace doesn't match" in locker.show_error.call_args[0][0]

    def test_invalid_number_format(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test non-numeric input is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("abc", "25", "5"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.show_error.assert_called_once()
        assert "valid numbers" in locker.show_error.call_args[0][0]


class TestVerifyStrengthData:
    """Tests for verify_strength_data method."""

    def test_valid_strength_data(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test valid strength data triggers unlock attempt."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "3", "10", "50", "1500"))
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        locker._attempt_unlock = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker._attempt_unlock.assert_called_once()

    def test_valid_multiple_exercises(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test valid data with multiple exercises."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(
            locker,
            StrengthData("Squat, Bench Press", "3, 3", "10, 8", "50, 40", "2460"),
        )
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        locker._attempt_unlock = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker._attempt_unlock.assert_called_once()

    def test_mismatched_list_lengths(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test mismatched list lengths are rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(
            locker,
            StrengthData("Squat, Bench", "3", "10, 8", "50, 40", "2000"),
        )
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "must match" in locker.show_error.call_args[0][0]

    def test_short_exercise_name(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test short exercise names are rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Sq", "3", "10", "50", "1500"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "too short" in locker.show_error.call_args[0][0]

    def test_invalid_sets_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test zero sets is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "0", "10", "50", "0"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "Sets" in locker.show_error.call_args[0][0]

    def test_invalid_sets_too_high(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test sets over max is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "25", "10", "50", "12500"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "Sets" in locker.show_error.call_args[0][0]

    def test_invalid_reps_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test zero reps is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "3", "0", "50", "0"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "Reps" in locker.show_error.call_args[0][0]

    def test_invalid_reps_too_high(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test reps over max is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "3", "150", "50", "22500"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "Reps" in locker.show_error.call_args[0][0]

    def test_invalid_weight_negative(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test negative weight is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "3", "10", "-10", "-300"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "Weights" in locker.show_error.call_args[0][0]

    def test_invalid_weight_too_high(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test weight over max is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "3", "10", "600", "18000"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "Weights" in locker.show_error.call_args[0][0]

    def test_total_weight_mismatch(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test total weight mismatch is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "3", "10", "50", "3000"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "Total weight doesn't match" in locker.show_error.call_args[0][0]

    def test_invalid_format(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test invalid format is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "abc", "10", "50", "1500"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "valid data" in locker.show_error.call_args[0][0]


class TestUITransitions:
    """Tests for UI state transitions."""

    def test_clear_container(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test clear_container destroys all child widgets."""
        locker = create_locker(mock_tk, tmp_path)

        # Set up mock children
        mock_child1 = MagicMock()
        mock_child2 = MagicMock()
        locker.container.winfo_children.return_value = [  # type: ignore[attr-defined]
            mock_child1,
            mock_child2,
        ]

        locker.clear_container()

        mock_child1.destroy.assert_called_once()
        mock_child2.destroy.assert_called_once()

    def test_unlock_screen_saves_and_schedules_close(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen saves log and schedules close."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}

        locker.unlock_screen()

        # Check that after() was called to schedule close
        locker.root.after.assert_called()  # type: ignore[attr-defined]

    def test_lockout_starts_countdown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
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

        locker.root.destroy.assert_called_once()  # type: ignore[attr-defined]
        mock_sys_exit.assert_called_with(0)


class TestTimerLogic:
    """Tests for timer countdown logic."""

    def test_update_lockout_countdown_decrements(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test countdown decrements remaining time."""
        locker = create_locker(mock_tk, tmp_path)
        locker.remaining_time = 5
        locker.countdown_label = MagicMock()

        locker.update_lockout_countdown()

        assert locker.remaining_time == 4
        locker.root.after.assert_called_with(  # type: ignore[attr-defined]
            1000, locker.update_lockout_countdown
        )

    def test_update_lockout_countdown_at_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test countdown at zero returns to workout question."""
        locker = create_locker(mock_tk, tmp_path)
        locker.remaining_time = 0
        locker.countdown_label = MagicMock()
        locker.ask_workout_done = MagicMock()  # type: ignore[method-assign]

        locker.update_lockout_countdown()

        locker.ask_workout_done.assert_called_once()

    def test_update_submit_timer_countdown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test submit timer counts down."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 5
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        locker.entries_to_check = []

        locker.update_submit_timer()

        assert locker.submit_unlock_time == 4
        locker.root.after.assert_called()  # type: ignore[attr-defined]

    def test_update_submit_timer_enables_when_filled(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test submit enabled when timer done and entries filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 0
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = "some value"
        locker.entries_to_check = [mock_entry]
        locker.submit_command = MagicMock()

        locker.update_submit_timer()

        locker.submit_btn.config.assert_called()

    def test_update_submit_timer_waits_for_entries(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test submit waits when entries not filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 0
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = ""  # Empty entry
        locker.entries_to_check = [mock_entry]

        locker.update_submit_timer()

        locker.root.after.assert_called_with(  # type: ignore[attr-defined]
            1000, locker.check_entries_filled
        )

    def test_update_submit_timer_handles_tcl_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test timer handles TclError when widgets destroyed."""
        locker = create_locker(mock_tk, tmp_path)
        locker.submit_unlock_time = 5
        locker.timer_label = MagicMock()
        locker.timer_label.config.side_effect = _TK_TCLERROR("widget destroyed")

        # Should not raise
        locker.update_submit_timer()

    def test_check_entries_filled_enables_submit(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test check_entries_filled enables submit when all filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = "value"
        locker.entries_to_check = [mock_entry]
        locker.submit_command = MagicMock()

        locker.check_entries_filled()

        locker.submit_btn.config.assert_called()

    def test_check_entries_filled_continues_waiting(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test check_entries_filled continues waiting when not filled."""
        locker = create_locker(mock_tk, tmp_path)
        locker.timer_label = MagicMock()
        locker.submit_btn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.return_value = ""
        locker.entries_to_check = [mock_entry]

        locker.check_entries_filled()

        locker.root.after.assert_called_with(  # type: ignore[attr-defined]
            1000, locker.check_entries_filled
        )

    def test_check_entries_filled_handles_tcl_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test check_entries_filled handles TclError."""
        locker = create_locker(mock_tk, tmp_path)
        locker.timer_label = MagicMock()
        mock_entry = MagicMock()
        mock_entry.get.side_effect = _TK_TCLERROR("widget destroyed")
        locker.entries_to_check = [mock_entry]

        # Should not raise
        locker.check_entries_filled()


class TestShowError:
    """Tests for show_error method."""

    def test_show_error_displays_message(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test show_error clears container and displays error."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]

        locker.show_error("Test error message")

        locker.clear_container.assert_called_once()


class TestRun:
    """Tests for run method."""

    def test_run_starts_mainloop(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test run starts the tkinter mainloop."""
        locker = create_locker(mock_tk, tmp_path)

        locker.run()

        locker.root.mainloop.assert_called_once()  # type: ignore[attr-defined]


class TestMainEntry:
    """Tests for main entry point."""

    def test_main_demo_mode_default(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test main defaults to demo mode."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)

        assert locker.demo_mode is True

    def test_main_production_mode_flag(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test main with --production flag."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)

        assert locker.demo_mode is False


class TestAskWorkoutType:
    """Tests for ask_workout_type method."""

    def test_ask_workout_type_creates_buttons(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_workout_type creates running and strength buttons."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]

        locker.ask_workout_type()

        locker.clear_container.assert_called_once()
        # Verify Label and Button were called
        mock_tk.Label.assert_called()
        mock_tk.Button.assert_called()


class TestAskRunningDetails:
    """Tests for ask_running_details method."""

    def test_ask_running_details_sets_workout_type(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_running_details sets workout type to running."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_running_details()

        assert locker.workout_data["type"] == "running"
        locker.clear_container.assert_called_once()

    def test_ask_running_details_creates_entry_fields(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_running_details creates entry fields."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_running_details()

        # Verify Entry fields were created
        mock_tk.Entry.assert_called()
        assert hasattr(locker, "distance_entry")
        assert hasattr(locker, "time_entry")
        assert hasattr(locker, "pace_entry")

    def test_ask_running_details_sets_timer(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_running_details initializes submit timer."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_running_details()

        assert locker.submit_unlock_time == SUBMIT_DELAY_DEMO
        locker.update_submit_timer.assert_called_once()


class TestAskStrengthDetails:
    """Tests for ask_strength_details method."""

    def test_ask_strength_details_sets_workout_type(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_strength_details sets workout type to strength."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        assert locker.workout_data["type"] == "strength"
        locker.clear_container.assert_called_once()

    def test_ask_strength_details_creates_entry_fields(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_strength_details creates entry fields."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        # Verify Entry fields were created
        mock_tk.Entry.assert_called()
        assert hasattr(locker, "exercises_entry")
        assert hasattr(locker, "sets_entry")
        assert hasattr(locker, "reps_entry")
        assert hasattr(locker, "weights_entry")
        assert hasattr(locker, "total_weight_entry")

    def test_ask_strength_details_sets_timer(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_strength_details initializes submit timer."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        assert locker.submit_unlock_time == SUBMIT_DELAY_DEMO
        locker.update_submit_timer.assert_called_once()

    def test_ask_strength_details_production_timer(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test production mode uses longer submit delay."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker.update_submit_timer = MagicMock()  # type: ignore[method-assign]

        locker.ask_strength_details()

        assert locker.submit_unlock_time == SUBMIT_DELAY_PRODUCTION


class TestAskWorkoutDone:
    """Tests for ask_workout_done method."""

    def test_ask_workout_done_creates_buttons(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ask_workout_done creates yes/no buttons."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]

        locker.ask_workout_done()

        locker.clear_container.assert_called_once()
        mock_tk.Label.assert_called()
        mock_tk.Button.assert_called()


class TestAdjustShutdownTimeLater:
    """Tests for _adjust_shutdown_time_later method."""

    def test_adjust_shutdown_time_later_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later adds hours successfully."""
        locker = create_locker(mock_tk, tmp_path)
        locker._read_shutdown_config = MagicMock(  # type: ignore[method-assign]
            return_value=(21, 22, 8)
        )
        locker._write_shutdown_config = MagicMock(  # type: ignore[method-assign]
            return_value=True
        )

        result = locker._adjust_shutdown_time_later()

        assert result is True
        locker._write_shutdown_config.assert_called_once_with(23, 23, 8, restore=True)

    def test_adjust_shutdown_time_later_caps_at_23(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later caps hours at 23."""
        locker = create_locker(mock_tk, tmp_path)
        locker._read_shutdown_config = MagicMock(  # type: ignore[method-assign]
            return_value=(22, 23, 8)
        )
        locker._write_shutdown_config = MagicMock(  # type: ignore[method-assign]
            return_value=True
        )

        result = locker._adjust_shutdown_time_later()

        assert result is True
        # 22+2=24 capped to 23, 23+2=25 capped to 23
        locker._write_shutdown_config.assert_called_once_with(23, 23, 8, restore=True)

    def test_adjust_shutdown_time_later_no_config(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later returns False if config missing."""
        locker = create_locker(mock_tk, tmp_path)
        locker._read_shutdown_config = MagicMock(  # type: ignore[method-assign]
            return_value=None
        )

        result = locker._adjust_shutdown_time_later()

        assert result is False

    def test_adjust_shutdown_time_later_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _adjust_shutdown_time_later handles OSError."""
        locker = create_locker(mock_tk, tmp_path)
        locker._read_shutdown_config = MagicMock(  # type: ignore[method-assign]
            side_effect=OSError("permission denied")
        )

        result = locker._adjust_shutdown_time_later()

        assert result is False


class TestRunAdb:
    """Tests for _run_adb ADB command execution."""

    def test_run_adb_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test successful ADB command."""
        locker = create_locker(mock_tk, tmp_path)
        mock_result = MagicMock(returncode=0, stdout="ok\n")
        with patch(
            "python_pkg.screen_locker.screen_lock.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            success, output = locker._run_adb(["devices"])

        assert success is True
        assert output == "ok\n"
        mock_run.assert_called_once()

    def test_run_adb_failure(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test failed ADB command."""
        locker = create_locker(mock_tk, tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")
        with patch(
            "python_pkg.screen_locker.screen_lock.subprocess.run",
            return_value=mock_result,
        ):
            success, _output = locker._run_adb(["devices"])

        assert success is False

    def test_run_adb_not_found(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ADB binary not found."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "python_pkg.screen_locker.screen_lock.subprocess.run",
            side_effect=FileNotFoundError("adb not found"),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert output == ""

    def test_run_adb_oserror(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ADB OSError."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "python_pkg.screen_locker.screen_lock.subprocess.run",
            side_effect=OSError("permission denied"),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert output == ""

    def test_run_adb_timeout(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ADB command timeout."""
        locker = create_locker(mock_tk, tmp_path)
        with patch(
            "python_pkg.screen_locker.screen_lock.subprocess.run",
            side_effect=subprocess.TimeoutExpired("adb", 15),
        ):
            success, output = locker._run_adb(["devices"])

        assert success is False
        assert output == ""


class TestAdbShell:
    """Tests for _adb_shell method."""

    def test_adb_shell_no_root(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ADB shell without root."""
        locker = create_locker(mock_tk, tmp_path)
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(True, "output"),
        )

        success, output = locker._adb_shell("ls /sdcard")

        locker._run_adb.assert_called_once_with(["shell", "ls /sdcard"])
        assert success is True
        assert output == "output"

    def test_adb_shell_with_root(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ADB shell with root."""
        locker = create_locker(mock_tk, tmp_path)
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(True, "output"),
        )

        success, _output = locker._adb_shell("ls /data", root=True)

        locker._run_adb.assert_called_once_with(
            ["shell", "su", "-c", "ls /data"],
        )
        assert success is True


class TestIsPhoneConnected:
    """Tests for _is_phone_connected method."""

    def test_phone_connected(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test phone detected as connected."""
        locker = create_locker(mock_tk, tmp_path)
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(
                True,
                "List of devices attached\nABC123\tdevice\n\n",
            ),
        )

        assert locker._is_phone_connected() is True

    def test_phone_not_connected(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test no phone connected."""
        locker = create_locker(mock_tk, tmp_path)
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(True, "List of devices attached\n\n"),
        )
        locker._try_wireless_reconnect = MagicMock(  # type: ignore[method-assign]
            return_value=False,
        )

        assert locker._is_phone_connected() is False

    def test_phone_offline(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test phone connected but offline."""
        locker = create_locker(mock_tk, tmp_path)
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(
                True,
                "List of devices attached\nABC123\toffline\n\n",
            ),
        )
        locker._try_wireless_reconnect = MagicMock(  # type: ignore[method-assign]
            return_value=False,
        )

        assert locker._is_phone_connected() is False

    def test_adb_command_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test ADB command failure."""
        locker = create_locker(mock_tk, tmp_path)
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(False, ""),
        )
        locker._try_wireless_reconnect = MagicMock(  # type: ignore[method-assign]
            return_value=False,
        )

        assert locker._is_phone_connected() is False


class TestFindHealthConnectDb:
    """Tests for _pull_stronglifts_db method."""

    def test_db_pulled_successfully(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test StrongLifts DB pulled from device."""
        locker = create_locker(mock_tk, tmp_path)
        locker._adb_shell = MagicMock(  # type: ignore[method-assign]
            return_value=(True, ""),
        )
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(True, ""),
        )

        result = locker._pull_stronglifts_db()

        assert result is not None
        locker._adb_shell.assert_called_once()
        locker._run_adb.assert_called_once()
        call_args = locker._run_adb.call_args[0][0]
        assert call_args[0] == "pull"

    def test_db_cat_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test returns None when cat command fails."""
        locker = create_locker(mock_tk, tmp_path)
        locker._adb_shell = MagicMock(  # type: ignore[method-assign]
            return_value=(False, ""),
        )

        assert locker._pull_stronglifts_db() is None

    def test_db_pull_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test returns None when adb pull fails."""
        locker = create_locker(mock_tk, tmp_path)
        locker._adb_shell = MagicMock(  # type: ignore[method-assign]
            return_value=(True, ""),
        )
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(False, ""),
        )

        assert locker._pull_stronglifts_db() is None

    def test_db_uses_correct_remote_path(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test uses the correct StrongLifts DB remote path."""
        locker = create_locker(mock_tk, tmp_path)
        locker._adb_shell = MagicMock(  # type: ignore[method-assign]
            return_value=(True, ""),
        )
        locker._run_adb = MagicMock(  # type: ignore[method-assign]
            return_value=(True, ""),
        )

        locker._pull_stronglifts_db()

        shell_cmd = locker._adb_shell.call_args[0][0]
        assert STRONGLIFTS_DB_REMOTE in shell_cmd


class TestCountTodayWorkouts:
    """Tests for _count_today_workouts method."""

    def test_workouts_found_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test workouts found today."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        # Insert a workout with today's timestamp (ms)
        import time

        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000),
        )
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 1

    def test_no_workouts_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test no workouts today."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        # Insert a workout from yesterday (24h+ ago)
        import time

        yesterday_ms = int((time.time() - 200000) * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", yesterday_ms, yesterday_ms + 3600000),
        )
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 0

    def test_invalid_db_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test returns 0 for invalid database file."""
        locker = create_locker(mock_tk, tmp_path)
        bad_file = tmp_path / "not_a_db.db"
        bad_file.write_text("not a database")

        assert locker._count_today_workouts(bad_file) == 0

    def test_missing_table_returns_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test returns 0 when workouts table doesn't exist."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE other (id TEXT)")
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 0

    def test_multiple_workouts_today(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test counts multiple workouts today correctly."""
        locker = create_locker(mock_tk, tmp_path)
        db_file = tmp_path / "sl_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE workouts "
            "(id TEXT PRIMARY KEY, start INTEGER, finish INTEGER)",
        )
        import time

        now_ms = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w1", now_ms, now_ms + 3600000),
        )
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?)",
            ("w2", now_ms + 100000, now_ms + 3700000),
        )
        conn.commit()
        conn.close()

        assert locker._count_today_workouts(db_file) == 2


class TestVerifyPhoneWorkout:
    """Tests for _verify_phone_workout method."""

    def test_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test workout verified on phone."""
        locker = create_locker(mock_tk, tmp_path)
        locker._is_phone_connected = MagicMock(  # type: ignore[method-assign]
            return_value=True,
        )
        locker._pull_stronglifts_db = MagicMock(  # type: ignore[method-assign]
            return_value=tmp_path / "sl.db",
        )
        locker._count_today_workouts = MagicMock(  # type: ignore[method-assign]
            return_value=2,
        )

        status, message = locker._verify_phone_workout()

        assert status == "verified"
        assert "2 session" in message

    def test_not_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test no workout found on phone."""
        locker = create_locker(mock_tk, tmp_path)
        locker._is_phone_connected = MagicMock(  # type: ignore[method-assign]
            return_value=True,
        )
        locker._pull_stronglifts_db = MagicMock(  # type: ignore[method-assign]
            return_value=tmp_path / "sl.db",
        )
        locker._count_today_workouts = MagicMock(  # type: ignore[method-assign]
            return_value=0,
        )

        status, message = locker._verify_phone_workout()

        assert status == "not_verified"
        assert "No workout" in message

    def test_no_phone(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test no phone connected."""
        locker = create_locker(mock_tk, tmp_path)
        locker._is_phone_connected = MagicMock(  # type: ignore[method-assign]
            return_value=False,
        )

        status, _ = locker._verify_phone_workout()

        assert status == "no_phone"

    def test_error_no_db(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test error when StrongLifts DB cannot be pulled."""
        locker = create_locker(mock_tk, tmp_path)
        locker._is_phone_connected = MagicMock(  # type: ignore[method-assign]
            return_value=True,
        )
        locker._pull_stronglifts_db = MagicMock(  # type: ignore[method-assign]
            return_value=None,
        )

        status, message = locker._verify_phone_workout()

        assert status == "error"
        assert "database" in message.lower()


class TestStartPhoneCheck:
    """Tests for _start_phone_check and _handle_startup_phone_result."""

    def test_start_phone_check_shows_checking_screen(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _start_phone_check shows checking message and starts check."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker._verify_phone_workout = MagicMock(  # type: ignore[method-assign]
            return_value=("no_phone", "No phone"),
        )
        locker._poll_phone_check = MagicMock()  # type: ignore[method-assign]

        locker._start_phone_check()

        locker.clear_container.assert_called()
        locker._poll_phone_check.assert_called_once()
        assert locker._phone_future is not None

    def test_handle_startup_verified_unlocks_directly(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test verified result shows success screen then unlocks via after()."""
        locker = create_locker(mock_tk, tmp_path)
        locker.unlock_screen = MagicMock()  # type: ignore[method-assign]
        locker.root.after = MagicMock()  # type: ignore[method-assign]

        locker._handle_startup_phone_result("verified", "Workout verified! (1 session)")

        # unlock_screen is deferred via root.after, not called directly
        locker.unlock_screen.assert_not_called()
        assert locker.workout_data["type"] == "phone_verified"
        locker.root.after.assert_called_once_with(1500, locker.unlock_screen)

    def test_handle_startup_not_verified_shows_block(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test not_verified result shows blocking screen with buttons."""
        locker = create_locker(mock_tk, tmp_path)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]
        locker._handle_startup_phone_result(
            "not_verified", "No workout found on phone today"
        )

        locker.clear_container.assert_called()

    def test_handle_startup_no_phone_shows_penalty(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test no_phone result triggers penalty with ask_workout_done as callback."""
        locker = create_locker(mock_tk, tmp_path)
        locker._show_phone_penalty = MagicMock()  # type: ignore[method-assign]

        locker._handle_startup_phone_result("no_phone", "No phone")

        locker._show_phone_penalty.assert_called_once()
        _, kwargs = locker._show_phone_penalty.call_args
        assert kwargs["on_done"] == locker.ask_workout_done

    def test_handle_startup_error_shows_penalty(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test error result triggers penalty with ask_workout_done as callback."""
        locker = create_locker(mock_tk, tmp_path)
        locker._show_phone_penalty = MagicMock()  # type: ignore[method-assign]

        locker._handle_startup_phone_result("error", "DB not found")

        locker._show_phone_penalty.assert_called_once()
        _, kwargs = locker._show_phone_penalty.call_args
        assert kwargs["on_done"] == locker.ask_workout_done

    def test_poll_phone_check_schedules_retry_when_pending(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _poll_phone_check reschedules itself when future is not done."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future: MagicMock = MagicMock()
        mock_future.done.return_value = False
        locker._phone_future = mock_future  # type: ignore[assignment]
        locker.root.after = MagicMock()  # type: ignore[method-assign]

        locker._poll_phone_check()

        locker.root.after.assert_called_once_with(500, locker._poll_phone_check)

    def test_poll_phone_check_routes_when_done(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _poll_phone_check calls result handler when future is done."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future: MagicMock = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = ("no_phone", "No phone")
        locker._phone_future = mock_future  # type: ignore[assignment]
        locker._handle_startup_phone_result = MagicMock()  # type: ignore[method-assign]

        locker._poll_phone_check()

        locker._handle_startup_phone_result.assert_called_once_with(
            "no_phone", "No phone"
        )


class TestAttemptUnlock:
    """Tests for _attempt_unlock method."""

    def test_attempt_unlock_calls_unlock_screen(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test _attempt_unlock calls unlock_screen directly."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        locker.unlock_screen = MagicMock()  # type: ignore[method-assign]

        locker._attempt_unlock()

        locker.unlock_screen.assert_called_once()


class TestShowPhonePenalty:
    """Tests for _show_phone_penalty and _update_phone_penalty methods."""

    def test_show_phone_penalty_demo_delay(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test demo mode uses short penalty delay."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]

        locker._show_phone_penalty("test message")

        # _update_phone_penalty is called once, decrementing by 1
        assert locker.phone_penalty_remaining == PHONE_PENALTY_DELAY_DEMO - 1

    def test_show_phone_penalty_production_delay(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test production mode uses long penalty delay."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        locker.clear_container = MagicMock()  # type: ignore[method-assign]

        locker._show_phone_penalty("test message")

        assert locker.phone_penalty_remaining == PHONE_PENALTY_DELAY_PRODUCTION - 1

    def test_update_phone_penalty_countdown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test phone penalty countdown decrements."""
        locker = create_locker(mock_tk, tmp_path)
        locker.phone_penalty_remaining = 5
        locker.phone_penalty_label = MagicMock()

        locker._update_phone_penalty()

        assert locker.phone_penalty_remaining == 4
        locker.phone_penalty_label.config.assert_called_once_with(text="5")
        locker.root.after.assert_called()  # type: ignore[attr-defined]

    def test_update_phone_penalty_at_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test phone penalty unlocks when timer reaches zero."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        locker.phone_penalty_remaining = 0
        locker.phone_penalty_label = MagicMock()
        locker.unlock_screen = MagicMock()  # type: ignore[method-assign]
        locker._phone_penalty_done_fn = locker.unlock_screen  # type: ignore[attr-defined]

        locker._update_phone_penalty()

        locker.unlock_screen.assert_called_once()


class TestUnlockScreenShutdownAdjustment:
    """Tests for unlock_screen shutdown time adjustment."""

    def test_unlock_screen_adjusts_for_running(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen adjusts shutdown for running workout."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}
        locker._adjust_shutdown_time_later = MagicMock(  # type: ignore[method-assign]
            return_value=True
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()

    def test_unlock_screen_adjusts_for_strength(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen adjusts shutdown for strength workout."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        locker._adjust_shutdown_time_later = MagicMock(  # type: ignore[method-assign]
            return_value=True
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()

    def test_unlock_screen_adjusts_for_phone_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen adjusts shutdown for phone-verified workout."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "phone_verified"}
        locker._adjust_shutdown_time_later = MagicMock(  # type: ignore[method-assign]
            return_value=True
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()

    def test_unlock_screen_skips_adjustment_for_sick_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen does not adjust for sick day."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "sick_day"}
        locker._adjust_shutdown_time_later = MagicMock(  # type: ignore[method-assign]
            return_value=True
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_not_called()

    def test_unlock_screen_skips_adjustment_no_type(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen does not adjust when no workout type."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {}
        locker._adjust_shutdown_time_later = MagicMock(  # type: ignore[method-assign]
            return_value=True
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_not_called()

    def test_unlock_screen_handles_adjustment_failure(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,  # noqa: ARG002
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen continues when adjustment fails."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}
        locker._adjust_shutdown_time_later = MagicMock(  # type: ignore[method-assign]
            return_value=False
        )

        # Should not raise, should continue with unlock
        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()
        locker.root.after.assert_called()  # type: ignore[attr-defined]
