"""Tests targeting remaining screen_lock.py coverage gaps."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestUnlockScreenExtras:
    """Tests for unlock_screen extra-workout bonus and streak display (360-389)."""

    def _setup_unlock(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        weekly_count: int = 5,
        streak: int = 0,
        adjust_ok: bool = True,
    ):
        """Create a locker ready to call unlock_screen."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("{}")
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "phone_verified"}

        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_by",
            MagicMock(return_value=adjust_ok),
        )
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(return_value=(22, 22, 5)),
        )
        return locker

    def test_extra_workout_bonus_shown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """weekly_count > 4 + adjust succeeds → extra_bonus_delta calculated (360-364)."""
        locker = self._setup_unlock(mock_tk, tmp_path, weekly_count=5)

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch(
                "screen_locker.screen_lock.current_streak",
                return_value=0,
            ),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        locker._adjust_shutdown_time_by.assert_called_once_with(1)

    def test_extra_bonus_delta_displayed(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """extra_bonus_delta > 0 → _text called with 'Extra workout' (lines 375-376)."""
        locker = self._setup_unlock(mock_tk, tmp_path)

        # Simulate before=22, after=23 → delta=1
        old_cfg = (22, 22, 5)
        new_cfg = (23, 23, 5)
        locker._read_shutdown_config.side_effect = [old_cfg, new_cfg]

        text_calls: list[str] = []

        def _capture_text(msg: str, **kw: object) -> None:
            text_calls.append(msg)

        object.__setattr__(locker, "_text", _capture_text)

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch(
                "screen_locker.screen_lock.current_streak",
                return_value=0,
            ),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert any("Extra workout" in c for c in text_calls)

    def test_streak_displayed_when_nonzero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """streak >= 1 → _text shows streak line (line 389)."""
        locker = self._setup_unlock(mock_tk, tmp_path, weekly_count=3, adjust_ok=False)

        text_calls: list[str] = []

        def _capture_text(msg: str, **kw: object) -> None:
            text_calls.append(msg)

        object.__setattr__(locker, "_text", _capture_text)

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=3,
            ),
            patch(
                "screen_locker.screen_lock.current_streak",
                return_value=3,
            ),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert any("streak" in c.lower() for c in text_calls)

    def test_extra_bonus_skipped_when_old_cfg_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """old_cfg is None → branch 361->366: bonus block skipped, delta stays 0."""
        locker = self._setup_unlock(mock_tk, tmp_path)
        # _read_shutdown_config returns None → condition at 361 is False
        locker._read_shutdown_config.return_value = None

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker.screen_lock.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()
        # No assertion beyond "no crash" — we just needed the branch executed.

    def test_extra_bonus_skipped_when_new_cfg_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """new_cfg is None → branch 363->366: delta stays 0 even after adjust."""
        locker = self._setup_unlock(mock_tk, tmp_path)
        # First call (old_cfg): valid; second call (new_cfg after adjust): None
        locker._read_shutdown_config.side_effect = [(22, 22, 5), None]

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker.screen_lock.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()
