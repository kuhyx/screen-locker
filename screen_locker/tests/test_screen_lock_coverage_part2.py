"""Tests targeting remaining screen_lock.py coverage gaps."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests._unlock_helpers import setup_unlock

if TYPE_CHECKING:
    from pathlib import Path


class TestUnlockScreenExtras:
    """unlock_screen's extra-workout bonus and streak display."""

    def test_extra_workout_bonus_shown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An additional same-day verified workout earns the +1h bonus."""
        locker = setup_unlock(
            mock_tk, tmp_path, weekly_count=5, seed_today_type="manual_workout"
        )

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch(
                "screen_locker._unlock_view.current_streak",
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
        """extra_bonus_delta > 0 → _text called with 'Extra workout'."""
        locker = setup_unlock(mock_tk, tmp_path, seed_today_type="manual_workout")

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
                "screen_locker._unlock_view.current_streak",
                return_value=0,
            ),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert any("Extra workout" in c for c in text_calls)

    def test_no_extra_bonus_when_adjust_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Additional verified workout but the +1h adjust fails → delta stays 0."""
        locker = setup_unlock(
            mock_tk,
            tmp_path,
            seed_today_type="manual_workout",
            adjust_ok=False,
        )

        text_calls: list[str] = []
        object.__setattr__(locker, "_text", lambda msg, **kw: text_calls.append(msg))

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert not any("Extra workout" in c for c in text_calls)

    def test_no_extra_bonus_when_new_config_unreadable(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Re-reading the shutdown config fails after the +1h → delta stays 0."""
        locker = setup_unlock(mock_tk, tmp_path, seed_today_type="manual_workout")
        # old_cfg readable, new_cfg unreadable → no delta can be computed.
        locker._read_shutdown_config.side_effect = [(22, 22, 5), None]

        text_calls: list[str] = []
        object.__setattr__(locker, "_text", lambda msg, **kw: text_calls.append(msg))

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert not any("Extra workout" in c for c in text_calls)
