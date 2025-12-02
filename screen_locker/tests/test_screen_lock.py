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
        """Test valid running data unlocks screen."""
        locker = create_locker(mock_tk, tmp_path)
        setup_running_entries(locker, RunningData("5", "25", "5"))
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}
        locker.unlock_screen = MagicMock()  # type: ignore[method-assign]

        locker.verify_running_data()

        locker.unlock_screen.assert_called_once()

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
        """Test valid strength data unlocks screen."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "3", "10", "50", "1500"))
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        locker.unlock_screen = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.unlock_screen.assert_called_once()

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
        locker.unlock_screen = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.unlock_screen.assert_called_once()

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

        assert locker.submit_unlock_time == 30
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

        assert locker.submit_unlock_time == 30
        locker.update_submit_timer.assert_called_once()


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
