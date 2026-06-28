"""Tests for _start_phone_check, polling, and startup result routing."""
# pylint: disable=protected-access,unused-argument

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestStartPhoneCheck:
    """Tests for _start_phone_check and _handle_startup_phone_result."""

    def test_start_phone_check_shows_checking_screen(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _start_phone_check shows checking message and starts check."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())
        object.__setattr__(
            locker,
            "_verify_phone_workout",
            MagicMock(
                return_value=("no_phone", "No phone"),
            ),
        )
        object.__setattr__(locker, "_poll_phone_check", MagicMock())

        locker._start_phone_check()

        locker.clear_container.assert_called()
        locker._poll_phone_check.assert_called_once()
        assert locker._phone_future is not None

    def test_handle_startup_verified_unlocks_directly(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test verified result shows success screen then unlocks via after()."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "unlock_screen", MagicMock())
        object.__setattr__(locker.root, "after", MagicMock())

        locker._handle_startup_phone_result("verified", "Workout verified! (1 session)")

        # unlock_screen is deferred via root.after, not called directly
        locker.unlock_screen.assert_not_called()
        assert locker.workout_data["type"] == "phone_verified"
        locker.root.after.assert_called_once_with(1500, locker.unlock_screen)

    def test_handle_startup_not_verified_shows_retry_and_sick(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test not_verified result tries RunnerUp fallback then shows retry+sick."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_retry_and_sick", MagicMock())
        object.__setattr__(
            locker,
            "_start_runnerup_fallback",
            MagicMock(side_effect=lambda cb: cb()),
        )
        locker._handle_startup_phone_result(
            "not_verified", "No workout found on phone today"
        )

        locker._show_retry_and_sick.assert_called_once()

    def test_handle_startup_too_short_shows_retry_and_sick(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test too_short result shows retry and sick buttons."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_retry_and_sick", MagicMock())
        locker._handle_startup_phone_result(
            "too_short", "Workout too short! 25 min logged, need at least 50 min."
        )

        locker._show_retry_and_sick.assert_called_once()
        call_args = locker._show_retry_and_sick.call_args[0][0]
        assert "too short" in call_args.lower()

    def test_handle_startup_stale_shows_retry_and_sick(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test stale result tries RunnerUp fallback then shows retry+sick."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_retry_and_sick", MagicMock())
        object.__setattr__(
            locker,
            "_start_runnerup_fallback",
            MagicMock(side_effect=lambda cb: cb()),
        )
        locker._handle_startup_phone_result("stale", "Workout too old")

        locker._show_retry_and_sick.assert_called_once()
        call_args = locker._show_retry_and_sick.call_args[0][0]
        assert "workout too old" in call_args.lower()

    def test_handle_startup_no_exercises_shows_retry_and_sick(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no_exercises result tries RunnerUp fallback then shows retry+sick."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_retry_and_sick", MagicMock())
        object.__setattr__(
            locker,
            "_start_runnerup_fallback",
            MagicMock(side_effect=lambda cb: cb()),
        )
        locker._handle_startup_phone_result("no_exercises", "No exercises found")

        locker._show_retry_and_sick.assert_called_once()
        call_args = locker._show_retry_and_sick.call_args[0][0]
        assert "no exercises found" in call_args.lower()

    def test_handle_startup_clock_tampered_shows_retry_and_sick(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test clock_tampered result shows retry and sick buttons."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_retry_and_sick", MagicMock())
        locker._handle_startup_phone_result(
            "clock_tampered",
            "System clock is 600s ahead",
        )

        locker._show_retry_and_sick.assert_called_once()
        call_args = locker._show_retry_and_sick.call_args[0][0]
        assert "clock" in call_args.lower()

    def test_handle_startup_no_phone_shows_penalty(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no_phone result tries RunnerUp fallback then shows penalty."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_phone_penalty", MagicMock())
        object.__setattr__(
            locker,
            "_start_runnerup_fallback",
            MagicMock(side_effect=lambda cb: cb()),
        )

        locker._handle_startup_phone_result("no_phone", "No phone")

        locker._show_phone_penalty.assert_called_once_with("No phone")

    def test_handle_startup_error_shows_penalty(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test error result tries RunnerUp fallback then shows penalty."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_phone_penalty", MagicMock())
        object.__setattr__(
            locker,
            "_start_runnerup_fallback",
            MagicMock(side_effect=lambda cb: cb()),
        )

        locker._handle_startup_phone_result("error", "DB not found")

        locker._show_phone_penalty.assert_called_once_with("DB not found")

    def test_poll_phone_check_schedules_retry_when_pending(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _poll_phone_check reschedules itself when future is not done."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future: MagicMock = MagicMock()
        mock_future.done.return_value = False
        object.__setattr__(locker, "_phone_future", mock_future)
        object.__setattr__(locker.root, "after", MagicMock())

        locker._poll_phone_check()

        locker.root.after.assert_called_once_with(500, locker._poll_phone_check)

    def test_poll_phone_check_routes_when_done(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _poll_phone_check calls result handler when future is done."""
        locker = create_locker(mock_tk, tmp_path)
        mock_future: MagicMock = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = ("no_phone", "No phone")
        object.__setattr__(locker, "_phone_future", mock_future)
        object.__setattr__(locker, "_handle_startup_phone_result", MagicMock())

        locker._poll_phone_check()

        locker._handle_startup_phone_result.assert_called_once_with(
            "no_phone", "No phone"
        )
