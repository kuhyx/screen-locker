"""Tests for _check_today_state_exits and scheduled-skip branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from screen_locker.screen_lock import ScreenLocker
from screen_locker.tests.conftest import create_locker

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
                "screen_locker.screen_lock.has_workout_skip_today",
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
                "screen_locker.screen_lock.has_workout_skip_today",
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
                "screen_locker.screen_lock.has_workout_skip_today",
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
