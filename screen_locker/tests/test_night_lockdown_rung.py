"""The workout lock does not re-arm after tonight's evening night-lockdown.

``gatelock.night_lockdown`` decides "has the evening lockdown happened?";
these tests pin screen-locker's binding of its path, the ladder rung that
honours it, and the status view's mirror of that rung.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _night_lockdown
from screen_locker._compliance_state import explain_lock_decision
from screen_locker._night_lockdown import (
    EVENING_LOCKDOWN_REASON,
    skip_after_evening_lockdown,
    tonights_lockdown,
)
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 10, 17, 22, 30).astimezone()
EVENING = datetime(2026, 10, 17, 21, 5).astimezone()


def _stamp(when: str) -> None:
    """Write the redirected stamp for a LOCAL wall-clock time."""
    epoch = int(datetime.fromisoformat(when).astimezone().timestamp())
    _night_lockdown.NIGHT_LOCKDOWN_STAMP.write_text(f"{epoch}\n")


class TestTonightsLockdown:
    """The binding reads the (redirected) stamp through gatelock."""

    def test_missing_stamp_is_no_lockdown(self) -> None:
        assert tonights_lockdown(NOW) is None

    def test_evening_stamp_today_is_tonights_lockdown(self) -> None:
        _stamp("2026-10-17T21:05")
        assert tonights_lockdown(NOW) == EVENING

    def test_morning_relock_today_is_not(self) -> None:
        _stamp("2026-10-17T04:01")
        assert tonights_lockdown(NOW) is None

    def test_yesterdays_evening_is_not(self) -> None:
        _stamp("2026-10-16T21:05")
        assert tonights_lockdown(NOW) is None

    def test_garbage_is_not(self) -> None:
        _night_lockdown.NIGHT_LOCKDOWN_STAMP.write_text("not an epoch")
        assert tonights_lockdown(NOW) is None


class TestSkipAfterEveningLockdown:
    """The rung on its own."""

    def test_no_lockdown_lets_the_lock_proceed(self) -> None:
        record_skip = MagicMock()
        with patch.object(_night_lockdown, "tonights_lockdown", return_value=None):
            assert skip_after_evening_lockdown(record_skip) is False
        record_skip.assert_not_called()

    def test_tonights_lockdown_records_the_skip(self) -> None:
        record_skip = MagicMock()
        with patch.object(_night_lockdown, "tonights_lockdown", return_value=EVENING):
            assert skip_after_evening_lockdown(record_skip) is True
        reason, detail = record_skip.call_args.args
        assert reason == EVENING_LOCKDOWN_REASON == "evening_lockdown_today"
        assert "21:05" in detail
        assert record_skip.call_args.kwargs == {"locked_at": EVENING.isoformat()}


def _fall_through_the_ladder(locker: object) -> ExitStack:
    """Every rung above the new one falls through (see test_lock_invariant)."""
    stack = ExitStack()
    for patcher in (
        patch.object(locker, "_is_scheduled_skip_today", return_value=False),
        patch.object(locker, "_ingest_synced_manual_workouts"),
        patch.object(locker, "_auto_fill_week_runnerup_bonus"),
        patch.object(locker, "_check_today_state_exits", return_value=False),
        patch.object(locker, "has_logged_today", return_value=False),
        patch("screen_locker._startup_checks.is_relaxed_day", return_value=False),
        patch("screen_locker._startup_checks.has_weekly_minimum", return_value=False),
        patch("screen_locker._startup_checks.process_week_transition", return_value=[]),
        patch(
            "screen_locker._startup_checks.reset_to_base_if_new_day",
            return_value=False,
        ),
    ):
        stack.enter_context(patcher)
    return stack


class TestLadder:
    """``_check_non_verify_exits`` reaching the enforce point."""

    def test_after_tonights_lockdown_the_lock_does_not_rearm(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch.object(_night_lockdown, "tonights_lockdown", return_value=EVENING),
            patch("screen_locker._startup_checks.record_decision") as record,
            patch.object(locker, "_check_heat_skip_exit") as heat,
            patch("screen_locker._startup_checks.apply_flat_bonuses_if_new") as bonus,
            _fall_through_the_ladder(locker),
        ):
            locker._check_non_verify_exits()
        assert [c.args[0].reason for c in record.call_args_list] == [
            "evening_lockdown_today"
        ]
        assert record.call_args.args[0].locked is False
        heat.assert_not_called()
        # Credits still land: the rung sits below the reset/bonus/ingest block.
        bonus.assert_called_once()
        mock_sys_exit.assert_called_once_with(0)

    def test_morning_relock_still_enforces(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        _stamp(f"{datetime.now(tz=UTC).astimezone():%Y-%m-%d}T04:01")
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch("screen_locker._startup_checks.record_decision") as record,
            patch.object(locker, "_check_heat_skip_exit", return_value="skipped"),
            patch("screen_locker._startup_checks.apply_flat_bonuses_if_new"),
            _fall_through_the_ladder(locker),
        ):
            locker._check_non_verify_exits()
        assert [c.args[0].reason for c in record.call_args_list] == ["enforced"]
        mock_sys_exit.assert_not_called()

    def test_other_conditions_name_tonights_lockdown(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with patch.object(_night_lockdown, "tonights_lockdown", return_value=EVENING):
            also = locker._other_conditions("enforced")
        assert "evening_lockdown_today" in str(also)


class TestStatusMirror:
    """``explain_lock_decision`` names the rung instead of ``would_lock``."""

    def _explain(self, tmp_path: Path, *, evening_lockdown: bool) -> object:
        return explain_lock_decision(
            log_file=tmp_path / "log.json",
            early_bird_pending_file=tmp_path / "early_bird_pending.json",
            weekly_minimum_met=False,
            relaxed_day=False,
            evening_lockdown=evening_lockdown,
        )

    def test_tonights_lockdown_is_the_terminal_stage(self, tmp_path: Path) -> None:
        result = self._explain(tmp_path, evening_lockdown=True)
        assert result.stage == "evening_lockdown_today"
        assert result.fired is False

    def test_without_it_the_chain_still_would_lock(self, tmp_path: Path) -> None:
        result = self._explain(tmp_path, evening_lockdown=False)
        assert result.stage == "would_lock"
