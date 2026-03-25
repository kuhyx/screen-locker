"""Tests for phone workout verification, phone check, and unlock operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker.screen_lock import (
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
)
from python_pkg.screen_locker.tests.conftest import create_locker

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
        """Test workout verified on phone."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_is_phone_connected",
            MagicMock(
                return_value=True,
            ),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(
                return_value=tmp_path / "sl.db",
            ),
        )
        object.__setattr__(
            locker,
            "_count_today_workouts",
            MagicMock(
                return_value=2,
            ),
        )

        status, message = locker._verify_phone_workout()

        assert status == "verified"
        assert "2 session" in message

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
            MagicMock(
                return_value=True,
            ),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(
                return_value=tmp_path / "sl.db",
            ),
        )
        object.__setattr__(
            locker,
            "_count_today_workouts",
            MagicMock(
                return_value=0,
            ),
        )

        status, message = locker._verify_phone_workout()

        assert status == "not_verified"
        assert "No workout" in message

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
            MagicMock(
                return_value=False,
            ),
        )

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
            MagicMock(
                return_value=True,
            ),
        )
        object.__setattr__(
            locker,
            "_pull_stronglifts_db",
            MagicMock(
                return_value=None,
            ),
        )

        status, message = locker._verify_phone_workout()

        assert status == "error"
        assert "database" in message.lower()


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

    def test_handle_startup_not_verified_shows_block(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test not_verified result shows blocking screen with buttons."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "clear_container", MagicMock())
        locker._handle_startup_phone_result(
            "not_verified", "No workout found on phone today"
        )

        locker.clear_container.assert_called()

    def test_handle_startup_no_phone_shows_penalty(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test no_phone result triggers penalty with ask_workout_done as callback."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_phone_penalty", MagicMock())

        locker._handle_startup_phone_result("no_phone", "No phone")

        locker._show_phone_penalty.assert_called_once()
        _, kwargs = locker._show_phone_penalty.call_args
        assert kwargs["on_done"] == locker.ask_workout_done

    def test_handle_startup_error_shows_penalty(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test error result triggers penalty with ask_workout_done as callback."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_show_phone_penalty", MagicMock())

        locker._handle_startup_phone_result("error", "DB not found")

        locker._show_phone_penalty.assert_called_once()
        _, kwargs = locker._show_phone_penalty.call_args
        assert kwargs["on_done"] == locker.ask_workout_done

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


class TestAttemptUnlock:
    """Tests for _attempt_unlock method."""

    def test_attempt_unlock_calls_unlock_screen(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test _attempt_unlock calls unlock_screen directly."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        object.__setattr__(locker, "unlock_screen", MagicMock())

        locker._attempt_unlock()

        locker.unlock_screen.assert_called_once()


class TestShowPhonePenalty:
    """Tests for _show_phone_penalty and _update_phone_penalty methods."""

    def test_show_phone_penalty_demo_delay(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test demo mode uses short penalty delay."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)
        object.__setattr__(locker, "clear_container", MagicMock())

        locker._show_phone_penalty("test message")

        # _update_phone_penalty is called once, decrementing by 1
        assert locker.phone_penalty_remaining == PHONE_PENALTY_DELAY_DEMO - 1

    def test_show_phone_penalty_production_delay(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test production mode uses long penalty delay."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        object.__setattr__(locker, "clear_container", MagicMock())

        locker._show_phone_penalty("test message")

        assert locker.phone_penalty_remaining == PHONE_PENALTY_DELAY_PRODUCTION - 1

    def test_update_phone_penalty_countdown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test phone penalty countdown decrements."""
        locker = create_locker(mock_tk, tmp_path)
        locker.phone_penalty_remaining = 5
        locker.phone_penalty_label = MagicMock()

        locker._update_phone_penalty()

        assert locker.phone_penalty_remaining == 4
        locker.phone_penalty_label.config.assert_called_once_with(text="5")
        locker.root.after.assert_called()

    def test_update_phone_penalty_at_zero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test phone penalty unlocks when timer reaches zero."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        locker.phone_penalty_remaining = 0
        locker.phone_penalty_label = MagicMock()
        object.__setattr__(locker, "unlock_screen", MagicMock())
        locker._phone_penalty_done_fn = locker.unlock_screen

        locker._update_phone_penalty()

        locker.unlock_screen.assert_called_once()


class TestUnlockScreenShutdownAdjustment:
    """Tests for unlock_screen shutdown time adjustment."""

    def test_unlock_screen_adjusts_for_running(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen adjusts shutdown for running workout."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()

    def test_unlock_screen_adjusts_for_strength(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen adjusts shutdown for strength workout."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "strength"}
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()

    def test_unlock_screen_adjusts_for_phone_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen adjusts shutdown for phone-verified workout."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "phone_verified"}
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()

    def test_unlock_screen_skips_adjustment_for_sick_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen does not adjust for sick day."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "sick_day"}
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_not_called()

    def test_unlock_screen_skips_adjustment_no_type(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen does not adjust when no workout type."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {}
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=True)
        )

        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_not_called()

    def test_unlock_screen_handles_adjustment_failure(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test unlock_screen continues when adjustment fails."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "workout_log.json"
        locker.workout_data = {"type": "running"}
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=False)
        )

        # Should not raise, should continue with unlock
        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()
        locker.root.after.assert_called()
