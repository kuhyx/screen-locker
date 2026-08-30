"""Tests for the read-only MCP server tools in ``_mcp``.

Helpers are patched at the ``_mcp`` module namespace (where they are imported),
keeping each tool's own logic under test while isolating the already-tested
leaf functions. ``get_status`` / ``explain_lock`` are exercised against a real
:class:`StatusSnapshot` so the ``dataclasses.asdict`` conversion (and its
JSON-friendliness) is covered for real, not mocked away.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from unittest.mock import patch

from screen_locker import _mcp
from screen_locker._compliance_state import (
    AutoUpgradeOpportunity,
    LockExplanation,
    PredicateResult,
)
from screen_locker._status_data import (
    DayStatus,
    ManualWorkoutBudgetStatus,
    ShutdownProjection,
    ShutdownProjectionDay,
    SickBudgetStatus,
    StatusSnapshot,
    WeeklySummary,
)


def _lock_explanation() -> LockExplanation:
    return LockExplanation(
        fired=True,
        stage="would_lock",
        reason="No skip condition applies.",
        trace=(PredicateResult("scheduled_skip", fired=False, reason="not a skip"),),
        auto_upgrade=AutoUpgradeOpportunity(
            would_attempt=False, via="none", reason="No pending opportunity."
        ),
        heat_skip_evaluated=False,
    )


def _snapshot() -> StatusSnapshot:
    day = DayStatus(
        date="2026-07-10",
        label="Fri Jul 10",
        entry_types=(),
        source="",
        counted=False,
        day_count=0,
        is_sick_day=False,
    )
    return StatusSnapshot(
        today=day,
        week=WeeklySummary(
            days=(day,), counted_count=2, minimum=4, remaining=2, extra=0
        ),
        bonus_hours_this_week=0,
        streak=1,
        early_bird_extended=False,
        shutdown=ShutdownProjection(
            tonight=(22, 22, 5),
            rest_of_week=(
                ShutdownProjectionDay(label="Mon", hour=21, speculative=False),
            ),
            next_week_preview=(
                ShutdownProjectionDay(label="Mon", hour=21, speculative=True),
            ),
            explanation="explanation text",
        ),
        lock_explanation=_lock_explanation(),
        sick_budget=SickBudgetStatus(
            used_7d=0,
            budget_7d=1,
            used_30d=0,
            budget_30d=3,
            used_90d=0,
            budget_90d=10,
            debt=0,
            exhausted=False,
        ),
        manual_workout_budget=ManualWorkoutBudgetStatus(
            used_7d=0, budget_7d=2, used_30d=0, budget_30d=5, exhausted=False
        ),
        generated_at="2026-07-10T12:00:00+00:00",
    )


class TestReadTools:
    def test_get_status_returns_json_friendly_asdict(self) -> None:
        snap = _snapshot()
        with patch.object(_mcp, "gather_status", return_value=snap) as gs:
            out = _mcp.get_status()
        gs.assert_called_once_with()
        assert out == asdict(snap)
        # asdict output must be pure JSON (no datetime/dataclass leaks).
        json.dumps(out)

    def test_get_summary_combines_line_and_state(self) -> None:
        with (
            patch.object(_mcp, "gather_status") as gs,
            patch.object(_mcp, "format_summary_line", return_value="LINE") as fsl,
            patch.object(_mcp, "compliance_state_word", return_value="ok") as csw,
        ):
            out = _mcp.get_summary()
        assert out == {"summary_line": "LINE", "compliance_state": "ok"}
        fsl.assert_called_once_with(gs.return_value)
        csw.assert_called_once_with(gs.return_value)

    def test_explain_lock_returns_lock_explanation_asdict(self) -> None:
        snap = _snapshot()
        with patch.object(_mcp, "gather_status", return_value=snap):
            out = _mcp.explain_lock()
        assert out == asdict(snap.lock_explanation)
        assert out["fired"] is True
        json.dumps(out)


class TestGetFlags:
    def test_flags_dict_and_predicate_wiring(self) -> None:
        with (
            patch.object(_mcp, "load_history", return_value="HIST") as lh,
            patch.object(_mcp, "has_logged_today", return_value=True) as hlt,
            patch.object(_mcp, "is_scheduled_skip_today", return_value=False) as iss,
            patch.object(_mcp, "is_early_bird_pending", return_value=True) as iep,
            patch.object(_mcp, "is_sick_day_today", return_value=False) as isd,
        ):
            out = _mcp.get_flags()
        assert out == {
            "has_logged_today": True,
            "is_scheduled_skip_today": False,
            "is_early_bird_pending": True,
            "is_sick_day_today": False,
        }
        lh.assert_called_once_with()
        hlt.assert_called_once_with(_mcp._LOG_FILE)
        iss.assert_called_once_with(_mcp.SCHEDULED_SKIPS_FILE)
        iep.assert_called_once_with(_mcp.EARLY_BIRD_PENDING_FILE)
        isd.assert_called_once_with("HIST")


def test_main_runs_stdio_server() -> None:
    with patch.object(_mcp.mcp, "run") as run:
        _mcp.main()
    run.assert_called_once_with()
