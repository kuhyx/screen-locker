"""Tests for _check_today_state_exits and scheduled-skip branches."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._temperature import TemperatureCheck
from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import create_locker, create_locker_relaxed_day

if TYPE_CHECKING:
    from pathlib import Path

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
            patch.object(locker, "_is_early_bird_pending", return_value=True),
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
            patch.object(locker, "_is_early_bird_pending", return_value=True),
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
            patch.object(locker, "_is_early_bird_pending", return_value=True),
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
            patch.object(locker, "_is_early_bird_pending", return_value=False),
            patch.object(locker, "_is_sick_day_today", return_value=True),
            patch.object(locker, "_try_auto_upgrade_sick_day", return_value=True),
        ):
            result = locker._check_today_state_exits()
        assert result is True

    def test_sick_day_no_upgrade_still_returns_true(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A sick day already marked today halts startup even when no real
        workout is found to upgrade it - sick_day no longer lives in
        workout_log.json, so this halt must be explicit (see
        _auto_upgrade.py's _check_today_state_exits), not an accidental
        side effect of has_logged_today() catching a leftover log entry."""
        locker = self._make_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "_is_early_bird_pending", return_value=False),
            patch.object(locker, "_is_sick_day_today", return_value=True),
            patch.object(locker, "_try_auto_upgrade_sick_day", return_value=False),
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
            patch.object(locker, "_is_early_bird_pending", return_value=False),
            patch.object(locker, "_is_sick_day_today", return_value=False),
            patch.object(locker, "has_logged_today", return_value=False),
            patch(
                "screen_locker._auto_upgrade.has_workout_skip_today",
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
            patch.object(locker, "_is_early_bird_pending", return_value=False),
            patch.object(locker, "_is_sick_day_today", return_value=False),
            patch.object(locker, "has_logged_today", return_value=False),
            patch(
                "screen_locker._auto_upgrade.has_workout_skip_today",
                return_value=False,
            ),
            patch.object(locker, "_is_early_bird_time", return_value=True),
            patch.object(locker, "_save_early_bird_pending"),
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
            patch.object(locker, "_is_early_bird_pending", return_value=False),
            patch.object(locker, "_is_sick_day_today", return_value=False),
            patch.object(locker, "has_logged_today", return_value=False),
            patch(
                "screen_locker._auto_upgrade.has_workout_skip_today",
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


class TestRelaxedDayCloseAndRun:
    """No LockWindow is built on a relaxed day; close()/run() use root."""

    def test_relaxed_day_close_and_run_use_root_directly(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        locker = create_locker_relaxed_day(mock_tk, tmp_path)
        assert locker._lock is None

        locker.run()
        locker.root.mainloop.assert_called_once()

        locker.close()
        locker.root.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# _check_non_verify_exits: heat-skip branch (reached after weekly minimum
# is not met — the only remaining same-day skip is genuine extreme heat)
# ---------------------------------------------------------------------------


class TestHeatSkipBranch:
    def test_not_too_hot_no_dialog_shown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=20.0, timed_out=False),
            ) as mock_hot,
            patch.object(ScreenLocker, "_show_heat_skip_dialog") as mock_dialog,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_hot.assert_called_once()
        mock_dialog.assert_not_called()
        mock_sys_exit.assert_not_called()

    def test_too_hot_and_user_confirms_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=35.0, timed_out=False),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog", return_value=True),
            patch.object(ScreenLocker, "_save_heat_skip_log") as mock_save,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_save.assert_called_once_with(35.0)
        mock_sys_exit.assert_called_once_with(0)

    def test_too_hot_but_user_declines_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=35.0, timed_out=False),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog", return_value=False),
            patch.object(ScreenLocker, "_save_heat_skip_log") as mock_save,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_save.assert_not_called()
        mock_sys_exit.assert_not_called()

    def test_fetch_timed_out_defaults_to_lock_no_dialog(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A timed-out temperature check must fail closed, not skip the lock."""
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=None, timed_out=True),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog") as mock_dialog,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_dialog.assert_not_called()
        mock_sys_exit.assert_not_called()

    def test_fetch_failed_defaults_to_lock_no_dialog(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A failed (non-timeout) temperature check must also fail closed."""
        with (
            patch(
                "screen_locker._startup_checks.has_weekly_minimum", return_value=False
            ),
            patch(
                "screen_locker._startup_checks.fetch_current_temp_with_status",
                return_value=TemperatureCheck(temp_celsius=None, timed_out=False),
            ),
            patch.object(ScreenLocker, "_show_heat_skip_dialog") as mock_dialog,
        ):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_dialog.assert_not_called()
        mock_sys_exit.assert_not_called()
