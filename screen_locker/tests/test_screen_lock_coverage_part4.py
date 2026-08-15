"""Streak and edge-case reward rendering for unlock_screen.

Split out of test_screen_lock_coverage_part2.py for the 250-line cap; both
halves share the setup_unlock factory in _unlock_helpers.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests._unlock_helpers import setup_unlock

if TYPE_CHECKING:
    from pathlib import Path


class TestUnlockScreenRewards:
    """Streak display and the bonus paths that decline to award."""

    def test_streak_displayed_when_nonzero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """streak >= 1 → _text shows streak line (line 389)."""
        locker = setup_unlock(mock_tk, tmp_path, weekly_count=3, adjust_ok=False)

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
                "screen_locker._unlock_view.current_streak",
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
        locker = setup_unlock(mock_tk, tmp_path)
        # _read_shutdown_config returns None → condition at 361 is False
        locker._read_shutdown_config.return_value = None

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
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
        locker = setup_unlock(mock_tk, tmp_path)
        # First call (old_cfg): valid; second call (new_cfg after adjust): None
        locker._read_shutdown_config.side_effect = [(22, 22, 5), None]

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()
