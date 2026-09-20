"""Tests for the pure, read-only predicates in _compliance_state.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker import _compliance_state
from screen_locker._sick_tracker import SickHistory

if TYPE_CHECKING:
    from pathlib import Path


class TestEarlyBirdWindowIsTheCarrot:
    """The window is whatever wake-alarm's signed file says -- no wall clock."""

    def test_no_clock_predicate_remains(self) -> None:
        assert not hasattr(_compliance_state, "_early_bird_window_open")

    def test_window_open_mirrors_wake_skip(self, tmp_path: Path) -> None:
        files = {
            "log_file": tmp_path / "log.json",
            "early_bird_pending_file": tmp_path / "eb.json",
        }
        open_ = _compliance_state.explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            weekly_minimum_met=False,
            relaxed_day=False,
            wake_skip=True,
        )
        shut = _compliance_state.explain_lock_decision(
            **files,
            sick_history=SickHistory(),
            weekly_minimum_met=False,
            relaxed_day=False,
            wake_skip=False,
        )
        assert open_.stage == "wake_alarm_skip"
        assert shut.stage == "would_lock"
