"""A declared test hold keeps every workout-locker path from showing a window.

``holds`` (kuhyx/utils, ``holds-v0.1.0``) answers "is a proctored-test hold
active?". These tests fake it with a stand-in module so they pin only
screen-locker's side: the rung, its placement below the bookkeeping, and the
fail-closed behaviour when the package cannot be read.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime
import logging
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker import _hold
from screen_locker._compliance_state import explain_lock_decision
from screen_locker._hold import (
    HOLD_REASON,
    skip_during_hold,
    watch_for_hold,
    workout_hold_active,
)
from screen_locker._status_data import gather_status
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 11, 5, 11, 5).astimezone()


class _FakeHolds:
    """A ``holds`` stand-in: ``covers`` returns the value, or raises it."""

    def __init__(self, covers: object) -> None:
        self._covers = covers
        self.calls: list[tuple[str, datetime | None]] = []

    def covers(self, gate: str, now: datetime | None = None) -> bool:
        """Record the call, then answer like ``holds.covers``."""
        self.calls.append((gate, now))
        if isinstance(self._covers, BaseException):
            raise self._covers
        return bool(self._covers)


def _fake_holds(*, covers: object) -> _FakeHolds:
    return _FakeHolds(covers)


@pytest.fixture(name="fake_holds")
def _fake_holds_fixture(monkeypatch: pytest.MonkeyPatch) -> _FakeHolds:
    """Install a covering ``holds`` for the duration of one test."""
    mod = _fake_holds(covers=True)
    monkeypatch.setitem(sys.modules, "holds", mod)
    return mod


class TestWorkoutHoldActive:
    """The wrapper around ``holds.covers("workout", now)``."""

    def test_covered_is_true_and_asks_for_the_workout_gate(
        self, fake_holds: _FakeHolds
    ) -> None:
        """An active hold reads True, asked about the 'workout' gate and now."""
        assert workout_hold_active(NOW) is True
        assert fake_holds.calls == [("workout", NOW)]

    def test_not_covered_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No active hold reads False."""
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=False))
        assert workout_hold_active(NOW) is False

    def test_import_error_fails_closed_and_says_so(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A missing package means the gate behaves normally, logged at error."""
        monkeypatch.setitem(sys.modules, "holds", None)
        with caplog.at_level(logging.ERROR, logger="screen_locker._hold"):
            assert workout_hold_active(NOW) is False
        assert "holds" in caplog.text
        assert "normal" in caplog.text

    def test_runtime_error_fails_closed_and_says_so(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A holds call that blows up means no hold, logged at error."""
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=OSError("boom")))
        with caplog.at_level(logging.ERROR, logger="screen_locker._hold"):
            assert workout_hold_active(NOW) is False
        assert "boom" in caplog.text

    def test_default_now_is_passed_through_as_none(
        self, fake_holds: _FakeHolds
    ) -> None:
        """Without ``now`` the clock is holds' own (None)."""
        assert workout_hold_active() is True
        assert fake_holds.calls == [("workout", None)]


class TestSkipDuringHold:
    """The rung on its own."""

    def test_no_hold_lets_the_ladder_proceed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without a hold the rung records nothing."""
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=False))
        record_skip = MagicMock()
        assert skip_during_hold(record_skip) is False
        record_skip.assert_not_called()

    def test_hold_records_the_skip(self, fake_holds: _FakeHolds) -> None:
        """An active hold records a test_hold_active skip."""
        record_skip = MagicMock()
        assert skip_during_hold(record_skip) is True
        reason, detail = record_skip.call_args.args
        assert reason == HOLD_REASON == "test_hold_active"
        assert "hold" in detail.lower()

    def test_the_seam_is_the_module_function(self) -> None:
        """Tests patch ``_hold.workout_hold_active``, never a from-import."""
        record_skip = MagicMock()
        with patch.object(_hold, "workout_hold_active", return_value=True):
            assert skip_during_hold(record_skip) is True


def _fall_through_the_ladder(locker: object) -> ExitStack:
    """Every rung above the hold rung falls through (see test_night_lockdown_rung)."""
    stack = ExitStack()
    for patcher in (
        patch.object(locker, "_is_scheduled_skip_today", return_value=False),
        patch.object(locker, "_ingest_synced_manual_workouts"),
        patch.object(locker, "_auto_fill_week_runnerup_bonus"),
        patch.object(locker, "_check_today_state_exits", return_value=False),
        patch.object(locker, "has_logged_today", return_value=False),
        patch("screen_locker._startup_checks.has_weekly_minimum", return_value=False),
        patch("screen_locker._startup_checks.process_week_transition", return_value=[]),
        patch(
            "screen_locker._startup_checks.reset_to_base_if_new_day",
            return_value=False,
        ),
    ):
        stack.enter_context(patcher)
    return stack


@pytest.mark.parametrize("relaxed", [True, False], ids=["relaxed_day", "strict_day"])
class TestLadder:
    """``_check_non_verify_exits`` during and outside a hold."""

    def test_hold_means_no_prompt_and_no_lock(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        relaxed: bool,
    ) -> None:
        """The hold skips before the optional prompt, the heat dialog or the lock."""
        # After construction: building the locker runs the ladder itself.
        locker = create_locker(mock_tk, tmp_path)
        mock_sys_exit.reset_mock()
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=True))
        with (
            patch("screen_locker._startup_checks.record_decision") as record,
            patch("screen_locker._startup_checks.is_relaxed_day", return_value=relaxed),
            patch.object(locker, "_check_heat_skip_exit") as heat,
            patch("screen_locker._startup_checks.apply_flat_bonuses_if_new") as bonus,
            _fall_through_the_ladder(locker),
        ):
            locker._check_non_verify_exits()
        assert [c.args[0].reason for c in record.call_args_list] == ["test_hold_active"]
        assert record.call_args.args[0].locked is False
        heat.assert_not_called()
        assert getattr(locker, "_relaxed_day_mode", False) is False
        # Credit bookkeeping above the rung is untouched.
        bonus.assert_called_once()
        mock_sys_exit.assert_called_once_with(0)

    def test_without_a_hold_the_ladder_is_unchanged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        relaxed: bool,
    ) -> None:
        """No hold: the relaxed prompt or the enforced lock still happen."""
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=False))
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch("screen_locker._startup_checks.record_decision") as record,
            patch("screen_locker._startup_checks.is_relaxed_day", return_value=relaxed),
            patch.object(locker, "_check_heat_skip_exit", return_value="x"),
            patch("screen_locker._startup_checks.apply_flat_bonuses_if_new"),
            _fall_through_the_ladder(locker),
        ):
            locker._check_non_verify_exits()
        expected = "relaxed_day" if relaxed else "enforced"
        assert [c.args[0].reason for c in record.call_args_list] == [expected]
        mock_sys_exit.assert_not_called()


class TestWatchForHold:
    """An already-open window closes within one poll of a hold starting."""

    def test_arms_a_poll_no_longer_than_thirty_seconds(self) -> None:
        """The first check is scheduled on the Tk loop, <= 30 s out."""
        root, close = MagicMock(), MagicMock()
        watch_for_hold(root, close)
        delay, _tick = root.after.call_args.args
        assert 0 < delay <= 30_000
        close.assert_not_called()

    def test_no_hold_rearms_and_does_not_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without a hold the tick only schedules the next one."""
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=False))
        root, close = MagicMock(), MagicMock()
        watch_for_hold(root, close)
        root.after.call_args.args[1]()
        assert root.after.call_count == 2
        close.assert_not_called()

    def test_hold_closes_the_window_and_stops_polling(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A hold that starts mid-window closes it, once, and says so."""
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=True))
        root, close = MagicMock(), MagicMock()
        watch_for_hold(root, close)
        with caplog.at_level(logging.WARNING, logger="screen_locker._hold"):
            root.after.call_args.args[1]()
        close.assert_called_once_with()
        assert root.after.call_count == 1
        assert "hold" in caplog.text

    def test_construction_arms_the_watch(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """A built locker has the watch armed on its own root and ``close``."""
        with patch("screen_locker.screen_lock.watch_for_hold") as watch:
            locker = create_locker(mock_tk, tmp_path)
        watch.assert_called_once_with(locker.root, locker.close)


class TestStatusMirror:
    """The status explainer names the hold instead of ``would_lock``."""

    def _explain(self, tmp_path: Path, *, hold: bool) -> object:
        return explain_lock_decision(
            log_file=tmp_path / "log.json",
            early_bird_pending_file=tmp_path / "early_bird_pending.json",
            weekly_minimum_met=False,
            relaxed_day=False,
            hold=hold,
        )

    def test_an_active_hold_is_the_terminal_stage(self, tmp_path: Path) -> None:
        """The explanation stops at test_hold_active without firing."""
        result = self._explain(tmp_path, hold=True)
        assert result.stage == "test_hold_active"
        assert result.fired is False

    def test_without_it_the_chain_still_would_lock(self, tmp_path: Path) -> None:
        """No hold: the explanation still reaches would_lock."""
        assert self._explain(tmp_path, hold=False).stage == "would_lock"

    def test_snapshot_reads_the_hold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``gather_status`` asks ``holds`` and the explanation follows it."""
        monkeypatch.setitem(sys.modules, "holds", _fake_holds(covers=True))
        snap = gather_status(
            log_file=tmp_path / "log.json",
            early_bird_pending_file=tmp_path / "early_bird_pending.json",
            extra_benefits_file=tmp_path / "extra.json",
            shutdown_config_file=tmp_path / "shutdown.conf",
            now=NOW,
        )
        assert snap.lock_explanation.stage == "test_hold_active"

    def test_other_conditions_name_the_hold(
        self, mock_tk: MagicMock, tmp_path: Path, fake_holds: _FakeHolds
    ) -> None:
        """A decision made for another reason still reports the hold as also=."""
        locker = create_locker(mock_tk, tmp_path)
        assert "test_hold_active" in str(locker._other_conditions("enforced"))
