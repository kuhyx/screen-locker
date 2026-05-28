"""Tests for phone workout verification, phone check, and unlock operations."""
# pylint: disable=protected-access,unused-argument

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestVerifyPhoneWorkout:
    """Tests for _verify_phone_workout method."""

    def test_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test workout verified on phone with sufficient duration."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(return_value=tmp_path / "sl.db"),
        )
        object.__setattr__(
            locker,
            "_count_today_workouts",
            MagicMock(return_value=2),
        )
        object.__setattr__(
            locker,
            "_is_workout_finish_recent",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_get_today_exercise_count",
            MagicMock(return_value=3),
        )
        object.__setattr__(
            locker,
            "_get_today_workout_duration_minutes",
            MagicMock(return_value=65.0),
        )

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(True, "Clock OK"),
        ):
            status, message = locker._verify_phone_workout()

        assert status == "verified"
        assert "2 session" in message
        assert "65 min" in message
        assert "3 exercise" in message

    def test_not_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no workout found on phone."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(return_value=tmp_path / "sl.db"),
        )
        object.__setattr__(
            locker,
            "_count_today_workouts",
            MagicMock(return_value=0),
        )

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(True, "Clock OK"),
        ):
            status, message = locker._verify_phone_workout()

        assert status == "not_verified"
        assert "No workout" in message

    def test_too_short(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test workout found but too short."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(return_value=tmp_path / "sl.db"),
        )
        object.__setattr__(
            locker,
            "_count_today_workouts",
            MagicMock(return_value=1),
        )
        object.__setattr__(
            locker,
            "_is_workout_finish_recent",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_get_today_exercise_count",
            MagicMock(return_value=3),
        )
        object.__setattr__(
            locker,
            "_get_today_workout_duration_minutes",
            MagicMock(return_value=25.0),
        )

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(True, "Clock OK"),
        ):
            status, message = locker._verify_phone_workout()

        assert status == "too_short"
        assert "25 min" in message
        assert "50 min" in message

    def test_no_phone(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no phone connected."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(return_value=False),
        )

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(True, "Clock OK"),
        ):
            status, _ = locker._verify_phone_workout()

        assert status == "no_phone"

    def test_error_no_db(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test error when StrongLifts DB cannot be pulled."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(return_value=None),
        )

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(True, "Clock OK"),
        ):
            status, message = locker._verify_phone_workout()

        assert status == "error"
        assert "database" in message.lower()

    def test_clock_tampered(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test clock_tampered when NTP check fails."""
        locker = create_locker(mock_tk, tmp_path)

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(False, "System clock is 600s ahead"),
        ):
            status, message = locker._verify_phone_workout()

        assert status == "clock_tampered"
        assert "600s" in message

    def test_stale_workout(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test stale status when workout finish is not recent."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(return_value=tmp_path / "sl.db"),
        )
        object.__setattr__(
            locker,
            "_count_today_workouts",
            MagicMock(return_value=1),
        )
        object.__setattr__(
            locker,
            "_is_workout_finish_recent",
            MagicMock(return_value=False),
        )

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(True, "Clock OK"),
        ):
            status, message = locker._verify_phone_workout()

        assert status == "stale"
        assert "old" in message.lower()

    def test_no_exercises(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no_exercises when workout has no exercise data."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(return_value=tmp_path / "sl.db"),
        )
        object.__setattr__(
            locker,
            "_count_today_workouts",
            MagicMock(return_value=1),
        )
        object.__setattr__(
            locker,
            "_is_workout_finish_recent",
            MagicMock(return_value=True),
        )
        object.__setattr__(
            locker,
            "_get_today_exercise_count",
            MagicMock(return_value=0),
        )

        with patch(
            "screen_locker._phone_verification.check_clock_skew",
            return_value=(True, "Clock OK"),
        ):
            status, message = locker._verify_phone_workout()

        assert status == "no_exercises"
        assert "exercise" in message.lower()
