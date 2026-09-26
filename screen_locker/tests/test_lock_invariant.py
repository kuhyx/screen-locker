"""Tests for the enforce-path guard in ``_lock_invariant``.

The ladder above the guard is exercised rung-by-rung elsewhere
(``test_weekly_logic_part2``). These tests force the whole ladder to fall
through -- the shape of every ordering bug it could ever have -- and check
that a logged workout still cannot be locked over.
"""

from __future__ import annotations

from contextlib import ExitStack
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._lock_invariant import (
    GUARD_DETAIL,
    GUARD_REASON,
    refuse_to_lock_over_logged_workout,
)
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestRefuseToLockOverLoggedWorkout:
    """The guard function on its own."""

    def test_nothing_logged_lets_the_lock_proceed(self) -> None:
        """No workout today: the guard is inert and records nothing."""
        record_skip = MagicMock()
        assert refuse_to_lock_over_logged_workout(lambda: False, record_skip) is False
        record_skip.assert_not_called()

    def test_logged_workout_records_the_guard_skip_and_logs_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A logged workout fires the guard: skip recorded, ERROR in the journal."""
        record_skip = MagicMock()
        with caplog.at_level(logging.ERROR, logger="screen_locker._lock_invariant"):
            assert refuse_to_lock_over_logged_workout(lambda: True, record_skip) is True
        record_skip.assert_called_once_with(GUARD_REASON, GUARD_DETAIL)
        assert any(
            record.levelno == logging.ERROR and "misordered" in record.getMessage()
            for record in caplog.records
        )


class TestEnforcePathChokepoint:
    """``_check_non_verify_exits`` with every rung above the guard falling through.

    ``_check_today_state_exits`` is stubbed to return False -- that is what an
    expired early-bird marker did on 2026-09-18, and what any future
    misordering of that ladder would do again -- so the only thing standing
    between a logged workout and a lock screen is the guard.
    """

    @staticmethod
    def _fall_through_the_ladder(locker: object) -> ExitStack:
        stack = ExitStack()
        for patcher in (
            patch.object(locker, "_is_scheduled_skip_today", return_value=False),
            patch.object(locker, "_ingest_synced_manual_workouts"),
            patch.object(locker, "_auto_fill_week_runnerup_bonus"),
            patch.object(locker, "_check_today_state_exits", return_value=False),
            patch.object(locker, "_check_heat_skip_exit", return_value="skipped"),
            patch(
                "screen_locker._startup_checks.process_week_transition", return_value=[]
            ),
            patch(
                "screen_locker._startup_checks.reset_to_base_if_new_day",
                return_value=False,
            ),
            patch("screen_locker._startup_checks.apply_flat_bonuses_if_new"),
        ):
            stack.enter_context(patcher)
        return stack

    def test_logged_workout_is_never_locked_over(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Ladder fell through with a workout logged: guard skip, no ``enforced``."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "has_logged_today", return_value=True),
            patch("screen_locker._startup_checks.record_decision") as record,
            self._fall_through_the_ladder(locker),
        ):
            locker._check_non_verify_exits()
        reasons = [call.args[0].reason for call in record.call_args_list]
        assert reasons == [GUARD_REASON]
        assert record.call_args.args[0].locked is False
        mock_sys_exit.assert_called_once_with(0)

    def test_no_workout_still_enforces(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Same fall-through with nothing logged: the lock goes ahead as before."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(locker, "has_logged_today", return_value=False),
            patch("screen_locker._startup_checks.record_decision") as record,
            self._fall_through_the_ladder(locker),
        ):
            locker._check_non_verify_exits()
        assert [call.args[0].reason for call in record.call_args_list] == ["enforced"]
        assert record.call_args.args[0].locked is True
        mock_sys_exit.assert_not_called()
