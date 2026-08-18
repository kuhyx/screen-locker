"""Tests for post-sick-day workout verification (--verify-workout)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestHandleVerifyWorkoutResult:
    """Tests for _handle_verify_workout_result."""

    def test_verified_adjusts_shutdown_and_saves(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On verified: adjust shutdown, save log, show success."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "log.json"
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_later",
            MagicMock(return_value=True),
        )

        locker._handle_verify_workout_result("verified", "1 session found")

        assert locker.workout_data["type"] == "phone_verified"
        assert locker.workout_data["after_sick_day"] == "true"
        locker._adjust_shutdown_time_later.assert_called_once()
        locker.root.after.assert_called()

    def test_verified_without_adjustment(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On verified but adjustment fails: still saves and shows success."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = tmp_path / "log.json"
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_later",
            MagicMock(return_value=False),
        )

        locker._handle_verify_workout_result("verified", "1 session found")

        assert locker.workout_data["type"] == "phone_verified"
        locker.root.after.assert_called()

    def test_not_verified_shows_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On not_verified: show retry screen."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_show_verify_retry",
            MagicMock(),
        )

        locker._handle_verify_workout_result(
            "not_verified",
            "No workout today",
        )

        locker._show_verify_retry.assert_called_once_with(
            "No workout today",
        )

    def test_error_shows_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """On error: show retry screen."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_show_verify_retry",
            MagicMock(),
        )

        locker._handle_verify_workout_result("error", "ADB failed")

        locker._show_verify_retry.assert_called_once_with("ADB failed")


class TestShowVerifyRetry:
    """Tests for _show_verify_retry."""

    def test_shows_retry_and_close_buttons(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Show TRY AGAIN and Close buttons."""
        locker = create_locker(mock_tk, tmp_path)

        locker._show_verify_retry("No workout found")

        # Verify container was cleared and buttons were packed
        locker.container.first.winfo_children.return_value = []
