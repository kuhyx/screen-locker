"""Tests for running and strength data verification."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker.tests.conftest import (
    RunningData,
    StrengthData,
    create_locker,
    setup_running_entries,
    setup_strength_entries,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestVerifyRunningData:
    """Tests for verify_running_data method."""

    def test_valid_running_data(
        self,
        mock_tk: MagicMock,
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
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
        _mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test invalid format is rejected."""
        locker = create_locker(mock_tk, tmp_path)
        setup_strength_entries(locker, StrengthData("Squat", "abc", "10", "50", "1500"))
        locker.show_error = MagicMock()  # type: ignore[method-assign]

        locker.verify_strength_data()

        locker.show_error.assert_called_once()
        assert "valid data" in locker.show_error.call_args[0][0]
