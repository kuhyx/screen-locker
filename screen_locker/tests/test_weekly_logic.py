"""Tests for weekly workout enforcement and relaxed-day (Tue-Thu) logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from python_pkg.screen_locker.screen_lock import ScreenLocker
from python_pkg.screen_locker.tests.conftest import (
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
            patch.object(ScreenLocker, "_is_sick_day_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "python_pkg.screen_locker.screen_lock.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "python_pkg.screen_locker.screen_lock.has_weekly_minimum",
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
            patch.object(ScreenLocker, "_is_sick_day_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "python_pkg.screen_locker.screen_lock.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "python_pkg.screen_locker.screen_lock.has_weekly_minimum",
                return_value=False,
            ),
            patch.object(ScreenLocker, "_setup_window") as mock_full,
            patch.object(ScreenLocker, "_setup_relaxed_day_window") as mock_small,
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_relaxed_day_flow"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_small.assert_called_once()
        mock_full.assert_not_called()

    def test_relaxed_day_no_grab_input(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch.object(Path, "resolve", return_value=tmp_path),
            patch.object(ScreenLocker, "has_logged_today", return_value=False),
            patch.object(ScreenLocker, "_is_sick_day_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_log", return_value=False),
            patch.object(ScreenLocker, "_is_early_bird_time", return_value=False),
            patch.object(
                ScreenLocker, "_try_auto_upgrade_early_bird", return_value=False
            ),
            patch(
                "python_pkg.screen_locker.screen_lock.is_relaxed_day",
                return_value=True,
            ),
            patch(
                "python_pkg.screen_locker.screen_lock.has_weekly_minimum",
                return_value=False,
            ),
            patch.object(ScreenLocker, "_grab_input") as mock_grab,
            patch.object(ScreenLocker, "_start_phone_check"),
            patch.object(ScreenLocker, "_start_relaxed_day_flow"),
            patch.object(ScreenLocker, "_start_verify_workout_check"),
        ):
            ScreenLocker(demo_mode=True)

        mock_grab.assert_not_called()

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
            "python_pkg.screen_locker.screen_lock.has_weekly_minimum",
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
            "python_pkg.screen_locker.screen_lock.has_weekly_minimum",
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
            "python_pkg.screen_locker.screen_lock.has_weekly_minimum",
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
            "python_pkg.screen_locker.screen_lock.has_weekly_minimum",
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
                "python_pkg.screen_locker._ui_flows.count_weekly_workouts",
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
                "python_pkg.screen_locker._ui_flows.count_weekly_workouts",
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
                "python_pkg.screen_locker._ui_flows.count_weekly_workouts",
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
    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_verified_calls_unlock_screen(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with patch.object(locker, "unlock_screen"):
            locker._handle_relaxed_phone_result("verified", "StrongLifts sync OK")

        assert locker.workout_data["type"] == "phone_verified"
        assert locker.workout_data["source"] == "StrongLifts sync OK"
        locker.root.after.assert_called()

    def test_not_verified_shows_relaxed_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with patch.object(locker, "_show_relaxed_retry") as mock_retry:
            locker._handle_relaxed_phone_result("not_verified", "no workout today")

        mock_retry.assert_called_once_with("no workout today", "not_verified")

    def test_too_short_shows_relaxed_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with patch.object(locker, "_show_relaxed_retry") as mock_retry:
            locker._handle_relaxed_phone_result("too_short", "only 20 min")

        mock_retry.assert_called_once_with("only 20 min", "too_short")

    def test_no_phone_shows_relaxed_retry(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with patch.object(locker, "_show_relaxed_retry") as mock_retry:
            locker._handle_relaxed_phone_result("no_phone", "ADB not found")

        mock_retry.assert_called_once_with("ADB not found", "no_phone")


class TestShowRelaxedRetry:
    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_shows_try_again_and_close_buttons(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_button") as mock_button,
            patch.object(locker, "_label"),
            patch.object(locker, "_text"),
            patch.object(locker, "_button_row", return_value=MagicMock()),
            patch.object(locker, "clear_container"),
        ):
            locker._show_relaxed_retry("msg", "not_verified")

        button_texts = " ".join(str(c.args) for c in mock_button.call_args_list)
        assert "TRY AGAIN" in button_texts
        assert "Close" in button_texts

    def test_no_sick_button(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_button") as mock_button,
            patch.object(locker, "_label"),
            patch.object(locker, "_text"),
            patch.object(locker, "_button_row", return_value=MagicMock()),
            patch.object(locker, "clear_container"),
        ):
            locker._show_relaxed_retry("msg", "not_verified")

        button_texts = " ".join(str(c.args) for c in mock_button.call_args_list)
        assert "sick" not in button_texts.lower()


# ---------------------------------------------------------------------------
# _check_today_state_exits: return True/False branches
# ---------------------------------------------------------------------------


class TestCheckTodayStateExits:
    """Cover all return True/False paths in _check_today_state_exits.

    sys.exit is mocked without side_effect so execution continues past it
    and the 'return True' statements are reachable.
    """

    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_early_bird_upgrade_success_returns_true(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_log", return_value=True),
            patch.object(locker, "_is_early_bird_time", return_value=False),
            patch.object(locker, "_try_auto_upgrade_early_bird", return_value=True),
        ):
            result = locker._check_today_state_exits()
        assert result is True

    def test_early_bird_upgrade_fail_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_log", return_value=True),
            patch.object(locker, "_is_early_bird_time", return_value=False),
            patch.object(locker, "_try_auto_upgrade_early_bird", return_value=False),
        ):
            result = locker._check_today_state_exits()
        assert result is False

    def test_early_bird_window_active_returns_true(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_log", return_value=True),
            patch.object(locker, "_is_early_bird_time", return_value=True),
        ):
            result = locker._check_today_state_exits()
        assert result is True

    def test_sick_day_auto_upgrade_returns_true(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_log", return_value=False),
            patch.object(locker, "_is_sick_day_log", return_value=True),
            patch.object(locker, "_try_auto_upgrade_sick_day", return_value=True),
        ):
            result = locker._check_today_state_exits()
        assert result is True

    def test_workout_skip_today_returns_true(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_log", return_value=False),
            patch.object(locker, "_is_sick_day_log", return_value=False),
            patch.object(locker, "has_logged_today", return_value=False),
            patch(
                "python_pkg.screen_locker.screen_lock.has_workout_skip_today",
                return_value=True,
            ),
        ):
            result = locker._check_today_state_exits()
        assert result is True

    def test_early_bird_time_returns_true(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_log", return_value=False),
            patch.object(locker, "_is_sick_day_log", return_value=False),
            patch.object(locker, "has_logged_today", return_value=False),
            patch(
                "python_pkg.screen_locker.screen_lock.has_workout_skip_today",
                return_value=False,
            ),
            patch.object(locker, "_is_early_bird_time", return_value=True),
            patch.object(locker, "_save_early_bird_log"),
        ):
            result = locker._check_today_state_exits()
        assert result is True

    def test_no_exit_conditions_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_log", return_value=False),
            patch.object(locker, "_is_sick_day_log", return_value=False),
            patch.object(locker, "has_logged_today", return_value=False),
            patch(
                "python_pkg.screen_locker.screen_lock.has_workout_skip_today",
                return_value=False,
            ),
            patch.object(locker, "_is_early_bird_time", return_value=False),
        ):
            result = locker._check_today_state_exits()
        assert result is False


class TestCheckNonVerifyExitsScheduledSkip:
    """Cover the return after scheduled-skip sys.exit in _check_non_verify_exits."""

    def test_scheduled_skip_return_reached(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(locker, "_is_scheduled_skip_today", return_value=True):
            locker._check_non_verify_exits()
        mock_sys_exit.assert_called_once_with(0)
