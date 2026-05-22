"""Tests for phone workout verification, phone check, and unlock operations."""
# pylint: disable=protected-access,unused-argument

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from python_pkg.screen_locker._constants import NO_PHONE_EXTRA_LOCKOUT_SECONDS
from python_pkg.screen_locker.screen_lock import (
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
)
from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


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
        """Test production mode uses long penalty delay (base + no-phone bump)."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=False)
        object.__setattr__(locker, "clear_container", MagicMock())

        locker._show_phone_penalty("test message")

        expected = PHONE_PENALTY_DELAY_PRODUCTION + NO_PHONE_EXTRA_LOCKOUT_SECONDS - 1
        assert locker.phone_penalty_remaining == expected

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
        """Test phone penalty calls done function when timer reaches zero."""
        locker = create_locker(mock_tk, tmp_path)
        locker.phone_penalty_remaining = 0
        locker.phone_penalty_label = MagicMock()
        mock_done = MagicMock()
        locker._phone_penalty_done_fn = mock_done

        locker._update_phone_penalty()

        mock_done.assert_called_once()

    def test_show_phone_penalty_default_callback_shows_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test default phone penalty callback shows retry+sick screen."""
        locker = create_locker(mock_tk, tmp_path, demo_mode=True)
        object.__setattr__(locker, "clear_container", MagicMock())
        object.__setattr__(locker, "_show_retry_and_sick", MagicMock())

        locker._show_phone_penalty("No phone connected")

        # Simulate timer reaching zero by calling the done function
        locker._phone_penalty_done_fn()
        locker._show_retry_and_sick.assert_called_once_with("No phone connected")


class TestUnlockScreenShutdownAdjustment:
    """Tests for unlock_screen shutdown time adjustment."""

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
        locker.workout_data = {"type": "phone_verified"}
        object.__setattr__(
            locker, "_adjust_shutdown_time_later", MagicMock(return_value=False)
        )

        # Should not raise, should continue with unlock
        locker.unlock_screen()

        locker._adjust_shutdown_time_later.assert_called_once()
        locker.root.after.assert_called()
