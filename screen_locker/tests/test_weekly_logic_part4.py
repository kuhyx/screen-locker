"""Tests for weekly workout enforcement and relaxed-day (Tue-Thu) logic."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import (
    create_locker,
)

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker.screen_lock import ScreenLocker


class TestStartRelaxedDayFlow:
    """StartRelaxedDayFlow."""

    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_shows_weekly_count_in_text(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Shows weekly count in text."""
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._ui_flows_relaxed.count_weekly_workouts",
                return_value=2,
            ),
            patch.object(locker, "_text") as mock_text,
            patch.object(locker, "_label"),
            patch.object(locker, "_button_row"),
            patch.object(locker, "_button"),
            patch.object(locker, "clear_container"),
        ):
            locker._start_relaxed_day_flow()

        all_text = " ".join(str(c) for c in mock_text.call_args_list)
        assert "2" in all_text
        assert "5" in all_text

    def test_skip_button_wires_close(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Skip button wires close."""
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._ui_flows_relaxed.count_weekly_workouts",
                return_value=0,
            ),
            patch.object(locker, "_button") as mock_button,
            patch.object(locker, "_label"),
            patch.object(locker, "_text"),
            patch.object(locker, "_button_row", return_value=MagicMock()),
            patch.object(locker, "clear_container"),
        ):
            locker._start_relaxed_day_flow()

        skip_cmds = [
            c.kwargs["command"]
            for c in mock_button.call_args_list
            if "Skip" in str(c.args)
        ]
        assert any(cmd == locker.close for cmd in skip_cmds)

    def test_log_button_wires_relaxed_phone_check(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Log button wires relaxed phone check."""
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._ui_flows_relaxed.count_weekly_workouts",
                return_value=1,
            ),
            patch.object(locker, "_button") as mock_button,
            patch.object(locker, "_label"),
            patch.object(locker, "_text"),
            patch.object(locker, "_button_row", return_value=MagicMock()),
            patch.object(locker, "clear_container"),
        ):
            locker._start_relaxed_day_flow()

        log_cmds = [
            c.kwargs["command"]
            for c in mock_button.call_args_list
            if "Log" in str(c.args)
        ]
        assert any(cmd == locker._start_relaxed_phone_check for cmd in log_cmds)


class TestStartRelaxedPhoneCheck:
    """StartRelaxedPhoneCheck."""

    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_submits_phone_verify_and_polls(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Submits phone verify and polls."""
        locker = self._make_locker(mock_tk, tmp_path)
        with patch.object(
            locker, "_verify_phone_workout", return_value=("verified", "ok")
        ):
            locker._start_relaxed_phone_check()

        assert locker._phone_future is not None
        locker.root.after.assert_called()

    def test_poll_routes_when_done(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Poll routes when done."""
        locker = self._make_locker(mock_tk, tmp_path)
        mock_future = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = ("verified", "ok")
        locker._phone_future = mock_future
        with patch.object(locker, "_handle_relaxed_phone_result") as mock_handle:
            locker._poll_relaxed_phone_check()
        mock_handle.assert_called_once_with("verified", "ok")

    def test_poll_waits_when_not_done(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Poll waits when not done."""
        locker = self._make_locker(mock_tk, tmp_path)
        mock_future = MagicMock()
        mock_future.done.return_value = False
        locker._phone_future = mock_future
        with patch.object(locker, "_handle_relaxed_phone_result") as mock_handle:
            locker._poll_relaxed_phone_check()
        mock_handle.assert_not_called()
        locker.root.after.assert_called_with(500, locker._poll_relaxed_phone_check)

    def test_poll_with_none_future_waits(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Poll with none future waits."""
        locker = self._make_locker(mock_tk, tmp_path)
        locker._phone_future = None
        with patch.object(locker, "_handle_relaxed_phone_result") as mock_handle:
            locker._poll_relaxed_phone_check()
        mock_handle.assert_not_called()


class TestHandleRelaxedPhoneResult:
    """Tests for _handle_relaxed_phone_result routing and the retry screen."""

    def test_verified_saves_and_schedules_unlock(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verified saves and schedules unlock."""
        locker = create_locker(mock_tk, tmp_path)
        locker._handle_relaxed_phone_result("verified", "Workout verified!")
        assert locker.workout_data["type"] == "phone_verified"
        assert locker.workout_data["source"] == "Workout verified!"
        locker.root.after.assert_called_with(1500, locker.unlock_screen)

    def test_non_verified_shows_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Non verified shows retry."""
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_show_relaxed_retry") as mock_retry:
            locker._handle_relaxed_phone_result("not_verified", "nope")
        mock_retry.assert_called_once_with("nope", "not_verified")

    def test_show_relaxed_retry_renders_buttons(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Show relaxed retry renders buttons."""
        locker = create_locker(mock_tk, tmp_path)
        locker._show_relaxed_retry("No workout", "not_verified")
        button_texts = {
            call.kwargs.get("text") for call in mock_tk.Button.call_args_list
        }
        assert "TRY AGAIN" in button_texts
        assert "Close (Skip)" in button_texts
