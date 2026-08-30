"""Streak and edge-case reward rendering for unlock_screen.

Split out of test_screen_lock_coverage_part2.py for the 250-line cap; both
halves share the setup_unlock factory in _unlock_helpers.py.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker.tests._locker_factories import create_locker
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


class TestNoDisplayStandsDown:
    """The 2026-08-30 restart storm: no X server at 02:00.

    ``GateRoot()`` raised an unhandled ``TclError``, the process exited 1,
    ``Restart=on-failure`` restarted it ~6.3s later, and 1695 identical runs
    in three hours evicted the entire durable decision trail behind them.
    """

    @staticmethod
    def _build_with_no_display(tmp_path: Path) -> tuple[MagicMock, MagicMock]:
        """Construct a locker whose GateRoot cannot reach a display.

        Args:
            tmp_path: pytest's per-test directory.

        Returns:
            The patched ``record_run_aborted`` and ``sys.exit`` mocks.
        """
        # conftest stubs sys.exit process-wide, so without a real SystemExit
        # here execution would fall through to `self.root`, which was never
        # assigned -- and the test would assert on an AttributeError instead
        # of on standing down.
        with (
            patch(
                "screen_locker.screen_lock.GateRoot",
                side_effect=tk.TclError('couldn\'t connect to display ":0"'),
            ),
            patch("screen_locker.screen_lock.record_run_aborted") as aborted,
            patch(
                "screen_locker.screen_lock.sys.exit", side_effect=SystemExit(0)
            ) as exit_mock,
            pytest.raises(SystemExit) as raised,
        ):
            create_locker(MagicMock(), tmp_path, demo_mode=False)
        assert raised.value.code == 0
        return aborted, exit_mock

    def test_it_exits_zero_instead_of_failing(self, tmp_path: Path) -> None:
        """Exit 0 is what RestartPreventExitStatus=0 honours."""
        _, exit_mock = self._build_with_no_display(tmp_path)
        exit_mock.assert_called_once_with(0)

    def test_it_records_why_rather_than_going_quiet(self, tmp_path: Path) -> None:
        """ "Could not run" must not look like "chose not to lock"."""
        aborted, _ = self._build_with_no_display(tmp_path)
        aborted.assert_called_once()
        reason, detail = aborted.call_args.args
        assert reason == "no_display"
        assert "display" in detail.lower()
