"""Pure, read-only predicates mirroring the lock-decision chain.

Single source of truth for the leaf checks walked by
``screen_lock.ScreenLocker._check_non_verify_exits`` and
``_auto_upgrade.AutoUpgradeMixin._check_today_state_exits``. The existing
mixins delegate their read-only checks to the functions here; this module
never touches ADB, sudo, subprocess, or the network, and never writes to
disk.
``explain_lock_decision`` re-derives the same ordered chain for the status
view. One branch is a deliberate simplification: when an early-bird pending
marker has expired, the real code attempts a live phone/RunnerUp
auto-upgrade whose outcome can't be known without ADB. Rather than guess,
this module always continues the trace as if that attempt had *not yet
resolved* (mirroring the real code's "auto-upgrade failed" fallthrough) and
surfaces the pending opportunity separately via ``AutoUpgradeOpportunity``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from screen_locker._compliance_predicates import (
    has_logged_today,
    is_early_bird_pending,
    is_relaxed_day_skipped_today,
    is_scheduled_skip_today,
    is_sick_day_today,
)
from screen_locker._compliance_trace import (
    AutoUpgradeOpportunity,
    LockExplanation,
    PredicateResult,
    StageContext,
    _stage,
    describe_auto_upgrade_opportunity,
    describe_degraded_sources,
)
from screen_locker._day import today_str as local_day

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from screen_locker._degraded_sources import DegradedSource

__all__ = [
    "AutoUpgradeOpportunity",
    "LockExplanation",
    "PredicateResult",
    "describe_auto_upgrade_opportunity",
    "explain_lock_decision",
    "has_logged_today",
    "is_early_bird_pending",
    "is_relaxed_day_skipped_today",
    "is_scheduled_skip_today",
    "is_sick_day_today",
]


@dataclass(frozen=True)
class _Step:
    """One predicate of the lock-decision chain, in evaluation order."""

    name: str
    reason_true: str
    reason_false: str
    terminal_reason: str | None = None
    note_when_false: bool = False


# Order mirrors ``_check_non_verify_exits`` / ``_check_today_state_exits``.
# ``early_bird_pending_expired`` is recorded but never terminal on its own: an
# expired pending marker still falls through toward a full lock, with the
# upgrade opportunity surfaced separately (see module docstring).
_CHAIN: tuple[_Step, ...] = (
    _Step(
        "scheduled_skip",
        "Today is in scheduled_skips.json (unconditional manual skip).",
        "Today is not a manually scheduled skip day.",
        "Manually scheduled skip day — no lock, no workout required.",
    ),
    _Step(
        "early_bird_pending_expired",
        "Logged in during the early-bird window and it has since closed "
        "with no workout confirmed yet.",
        "No expired early-bird pending marker.",
    ),
    _Step(
        "early_bird_window_open",
        "Logged in during the early-bird window earlier today; still "
        "waiting to see a workout before the window closes.",
        "Not pending inside an open early-bird window.",
        "Early-bird window still open — lock skipped while waiting for a workout.",
    ),
    _Step(
        "sick_day",
        "Today is a sick day in the shared sickdays pool.",
        "Today is not a sick day.",
        "Sick day today — lock skipped.",
    ),
    _Step(
        "already_logged",
        "A validly-signed workout is already logged for today.",
        "No workout logged for today yet.",
        "Workout already logged today — lock skipped.",
        note_when_false=True,
    ),
    _Step(
        "wake_alarm_skip",
        "The morning session earned a workout skip for now.",
        "No morning-session skip in force.",
        "Morning session earned a skip — lock skipped.",
    ),
    _Step(
        "test_hold_active",
        "A declared test hold is active.",
        "No test hold active.",
        "Test hold active — no workout window until it ends.",
    ),
    _Step(
        "relaxed_day_already_skipped",
        "Relaxed day already dismissed via Skip — No Penalty today.",
        "No same-day relaxed-day dismissal on record.",
        "Relaxed day already skipped today — lock skipped, prompt not shown again.",
    ),
    _Step(
        "relaxed_day",
        "Today is a relaxed day (Tue/Wed/Thu).",
        "Today is not a relaxed day.",
        "Relaxed day (Tue/Wed/Thu) — workout optional, lock skipped.",
    ),
    _Step(
        "weekly_minimum_met",
        "Weekly workout minimum already reached.",
        "Weekly workout minimum not yet reached.",
        "Weekly workout minimum already met — lock skipped.",
    ),
    _Step(
        "evening_lockdown_today",
        "Tonight's night lockdown already fired (>= 12:00 today).",
        "No evening night lockdown yet today.",
        "Night lockdown already happened tonight — the workout lock does not re-arm.",
    ),
)


def _chain_flags(
    *,
    log_file: Path,
    weekly_minimum_met: bool,
    relaxed_day: bool,
    wake_skip: bool,
    evening_lockdown: bool,
    hold: bool,
    local_dt: datetime,
    pending: bool,
) -> dict[str, bool]:
    """Evaluate every predicate once; the keys are the ``_CHAIN`` step names."""
    today_str = local_day(local_dt)
    # The early-bird window IS the wake-alarm carrot (EarlyBirdMixin).
    return {
        "scheduled_skip": is_scheduled_skip_today(local_dt.date()),
        "early_bird_pending_expired": pending and not wake_skip,
        "early_bird_window_open": pending and wake_skip,
        "sick_day": is_sick_day_today(local_dt.date()),
        "already_logged": has_logged_today(log_file, today=today_str),
        "wake_alarm_skip": wake_skip,
        "test_hold_active": hold,
        "relaxed_day_already_skipped": relaxed_day
        and is_relaxed_day_skipped_today(log_file, today=today_str),
        "relaxed_day": relaxed_day,
        "weekly_minimum_met": weekly_minimum_met,
        "evening_lockdown_today": evening_lockdown,
    }


def _walk_chain(
    fired: dict[str, bool], context: StageContext, degraded_note: str
) -> LockExplanation | None:
    """Record each step in ``context.trace``; return the first terminal one."""
    for step in _CHAIN:
        hit = fired[step.name]
        reason = step.reason_true if hit else step.reason_false
        if step.note_when_false and not hit:
            reason += degraded_note
        context.trace.append(PredicateResult(step.name, hit, reason))
        if hit and step.terminal_reason is not None:
            return _stage(
                fired=False,
                stage=step.name,
                reason=step.terminal_reason,
                context=context,
            )
    return None


def explain_lock_decision(
    *,
    log_file: Path,
    early_bird_pending_file: Path,
    weekly_minimum_met: bool,
    relaxed_day: bool,
    wake_skip: bool = False,
    evening_lockdown: bool = False,
    hold: bool = False,
    now: datetime | None = None,
    degraded_sources: Sequence[DegradedSource] = (),
) -> LockExplanation:
    """Re-derive the lock-decision chain without ADB, sudo, or writes.

    Mirrors ``_check_non_verify_exits`` / ``_check_today_state_exits`` in
    order. Heat-skip is never evaluated (it needs a live ``wttr.in`` call) —
    reported via ``heat_skip_evaluated=False``, not guessed.
    """
    instant = now if now is not None else datetime.now(tz=UTC)
    pending = is_early_bird_pending(early_bird_pending_file, today=local_day(instant))
    fired = _chain_flags(
        log_file=log_file,
        weekly_minimum_met=weekly_minimum_met,
        relaxed_day=relaxed_day,
        wake_skip=wake_skip,
        evening_lockdown=evening_lockdown,
        hold=hold,
        local_dt=instant.astimezone(),
        pending=pending,
    )
    auto_upgrade = describe_auto_upgrade_opportunity(
        early_bird_pending=pending,
        early_bird_window_open=wake_skip,
    )
    context = StageContext([], auto_upgrade, bool(degraded_sources))
    degraded_note = describe_degraded_sources(degraded_sources)
    terminal = _walk_chain(fired, context, degraded_note)
    if terminal is not None:
        return terminal

    # Named for the conclusion; "..._pending_heat_check" read as "stuck".
    return _stage(
        fired=True,
        stage="would_lock",
        reason=(
            "No skip condition applies, so a locker run starting now would "
            "lock. This page re-derives the decision only: no live "
            "temperature is checked, and a run may or may not be happening "
            "right now (see Health)." + degraded_note
        ),
        context=context,
    )
