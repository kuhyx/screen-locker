"""Tests for weekly workout enforcement and relaxed-day (Tue-Thu) logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import (
    create_locker,
    create_locker_relaxed_day,
)

# ---------------------------------------------------------------------------
# _check_non_verify_exits: relaxed-day branch
# ---------------------------------------------------------------------------


class TestRelaxedDayBranch:
    def test_relaxed_day_sets_flag_instead_of_exiting(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = create_locker_relaxed_day(mock_tk, tmp_path)
        assert locker._relaxed_day_mode is True
        mock_sys_exit.assert_not_called()

    def test_relaxed_day_calls_start_relaxed_flow(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "screen_locker.screen_lock.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "screen_locker.screen_lock.has_weekly_minimum",
                return_value=False,
            ),
            patch.object(ScreenLocker, "_start_phone_check") as mock_phone,
            patch.object(ScreenLocker, "_start_relaxed_day_flow") as mock_relaxed,
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_relaxed.assert_called_once()
        mock_phone.assert_not_called()

    def test_relaxed_day_uses_small_window_not_fullscreen(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "screen_locker.screen_lock.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "screen_locker.screen_lock.has_weekly_minimum",
                return_value=False,
            ),
            patch("screen_locker.screen_lock.LockWindow") as mock_lock_window,
            patch.object(ScreenLocker, "_setup_relaxed_day_window") as mock_small,
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_relaxed_day_flow"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_small.assert_called_once()
        mock_lock_window.assert_not_called()

    def test_relaxed_day_no_grab_input(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_today", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_pending", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "screen_locker.screen_lock.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "screen_locker.screen_lock.has_weekly_minimum",
                return_value=False,
            ),
            patch("screen_locker.screen_lock.LockWindow") as mock_lock_window,
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_relaxed_day_flow"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_lock_window.assert_not_called()

    def test_has_logged_today_exits_before_relaxed_check(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_locker_relaxed_day(mock_tk, tmp_path, has_logged=True)
        mock_sys_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# _check_non_verify_exits: Fri-Mon weekly minimum branch
# ---------------------------------------------------------------------------


class TestWeeklyMinimumBranch:
    def test_weekly_minimum_met_exits(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch(
            "screen_locker.screen_lock.has_weekly_minimum",
            return_value=True,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_called_once_with(0)

    def test_weekly_minimum_not_met_shows_full_lock(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        # create_locker already stubs _start_phone_check; just verify no exit
        # and _relaxed_day_mode stays False (full lock path taken).
        with patch(
            "screen_locker.screen_lock.has_weekly_minimum",
            return_value=False,
        ):
            locker = create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_not_called()
        assert locker._relaxed_day_mode is False

    def test_weekly_minimum_not_checked_on_relaxed_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch(
            "screen_locker.screen_lock.has_weekly_minimum",
        ) as mock_weekly:
            create_locker_relaxed_day(mock_tk, tmp_path)

        mock_weekly.assert_not_called()

    def test_has_logged_exits_before_weekly_check(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with patch(
            "screen_locker.screen_lock.has_weekly_minimum",
        ) as mock_weekly:
            create_locker(mock_tk, tmp_path, has_logged=True)

        mock_weekly.assert_not_called()


# ---------------------------------------------------------------------------
# Relaxed-day UI flow methods
# ---------------------------------------------------------------------------


class TestStartRelaxedDayFlow:
    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_shows_weekly_count_in_text(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
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
        assert "4" in all_text

    def test_skip_button_wires_close(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
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
    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_submits_phone_verify_and_polls(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
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
        locker = create_locker(mock_tk, tmp_path)
        locker._show_relaxed_retry("No workout", "not_verified")
        button_texts = {
            call.kwargs.get("text") for call in mock_tk.Button.call_args_list
        }
        assert "TRY AGAIN" in button_texts
        assert "Close (Skip)" in button_texts
