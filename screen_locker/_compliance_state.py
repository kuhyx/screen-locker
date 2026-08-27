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

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from screen_locker._compliance_predicates import (
    _early_bird_window_open,
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

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from screen_locker._degraded_sources import DegradedSource
    from screen_locker._sick_tracker import SickHistory

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


def explain_lock_decision(
    *,
    log_file: Path,
    scheduled_skips_file: Path,
    early_bird_pending_file: Path,
    sick_history: SickHistory,
    extended_early_bird: bool,
    weekly_minimum_met: bool,
    relaxed_day: bool,
    wake_skip: bool = False,
    now: datetime | None = None,
    degraded_sources: Sequence[DegradedSource] = (),
) -> LockExplanation:
    """Re-derive the lock-decision chain without ADB, sudo, or writes.

    Mirrors ``_check_non_verify_exits`` / ``_check_today_state_exits`` in
    order. Heat-skip is never evaluated (it needs a live ``wttr.in`` call) —
    reported via ``heat_skip_evaluated=False``, not guessed.
    """
    instant = now if now is not None else datetime.now(tz=timezone.utc)
    today_str = instant.astimezone(timezone.utc).strftime("%Y-%m-%d")
    local_dt = instant.astimezone()
    local_minutes = local_dt.hour * 60 + local_dt.minute

    scheduled = is_scheduled_skip_today(scheduled_skips_file, today=today_str)
    pending = is_early_bird_pending(early_bird_pending_file, today=today_str)
    window_open = _early_bird_window_open(
        extended=extended_early_bird, local_minutes=local_minutes
    )
    expired = pending and not window_open
    early_bird_open_and_pending = pending and window_open
    window_end_label = "09:00" if extended_early_bird else "08:30"
    sick_today = is_sick_day_today(sick_history, today=today_str)
    logged = has_logged_today(log_file, today=today_str)
    relaxed_day_already_skipped = relaxed_day and is_relaxed_day_skipped_today(
        log_file, today=today_str
    )

    auto_upgrade = describe_auto_upgrade_opportunity(
        early_bird_pending=pending,
        early_bird_window_open=window_open,
        is_sick_day=sick_today,
    )

    trace: list[PredicateResult] = []
    stage_context = StageContext(trace, auto_upgrade, bool(degraded_sources))

    def _check(
        name: str,
        *,
        fired: bool,
        reason_true: str,
        reason_false: str,
        terminal_reason: str | None = None,
    ) -> LockExplanation | None:
        """Record one trace step; return an explanation if it terminates the chain."""
        reason = reason_true if fired else reason_false
        trace.append(PredicateResult(name, fired, reason))
        if fired and terminal_reason is not None:
            return _stage(
                fired=False,
                stage=name,
                reason=terminal_reason,
                context=stage_context,
            )
        return None

    result = _check(
        "scheduled_skip",
        fired=scheduled,
        reason_true="Today is in scheduled_skips.json (unconditional manual skip).",
        reason_false="Today is not a manually scheduled skip day.",
        terminal_reason="Manually scheduled skip day — no lock, no workout required.",
    )
    if result is not None:
        return result

    # Recorded but never terminal on its own: an expired pending marker still
    # falls through toward a full lock, with the upgrade opportunity surfaced
    # separately via `auto_upgrade` (see module docstring).
    _check(
        "early_bird_pending_expired",
        fired=expired,
        reason_true="Logged in during the early-bird window and it has since closed "
        "with no workout confirmed yet.",
        reason_false="No expired early-bird pending marker.",
    )

    result = _check(
        "early_bird_window_open",
        fired=early_bird_open_and_pending,
        reason_true="Logged in during the early-bird window earlier today; still "
        "waiting to see a workout before the window closes.",
        reason_false="Not pending inside an open early-bird window.",
        terminal_reason=(
            "Early-bird window still open — lock skipped while waiting for a workout."
        ),
    )
    if result is not None:
        return result

    result = _check(
        "sick_day",
        fired=sick_today,
        reason_true="Today is marked as a sick day in sick_history.json.",
        reason_false="Today is not marked as a sick day.",
        terminal_reason="Sick day logged today — lock skipped.",
    )
    if result is not None:
        return result

    degraded_note = describe_degraded_sources(degraded_sources)
    result = _check(
        "already_logged",
        fired=logged,
        reason_true="A validly-signed workout is already logged for today.",
        reason_false="No workout logged for today yet." + degraded_note,
        terminal_reason="Workout already logged today — lock skipped.",
    )
    if result is not None:
        return result

    result = _check(
        "wake_alarm_skip",
        fired=wake_skip,
        reason_true="Wake-alarm earned a workout skip for today.",
        reason_false="No wake-alarm workout skip earned today.",
        terminal_reason="Wake-alarm earned a workout skip — lock skipped.",
    )
    if result is not None:
        return result

    result = _check(
        "early_bird_time_fresh",
        fired=window_open,
        reason_true=(
            f"Currently inside the early-bird window (05:00-{window_end_label})."
        ),
        reason_false="Not currently inside the early-bird window.",
        terminal_reason="Inside the early-bird window — lock skipped, pending marker "
        f"would be saved for the {window_end_label} re-check.",
    )
    if result is not None:
        return result

    result = _check(
        "relaxed_day_already_skipped",
        fired=relaxed_day_already_skipped,
        reason_true="Relaxed day already dismissed via Skip — No Penalty today.",
        reason_false="No same-day relaxed-day dismissal on record.",
        terminal_reason="Relaxed day already skipped today — lock skipped, "
        "prompt not shown again.",
    )
    if result is not None:
        return result

    result = _check(
        "relaxed_day",
        fired=relaxed_day,
        reason_true="Today is a relaxed day (Tue/Wed/Thu).",
        reason_false="Today is not a relaxed day.",
        terminal_reason="Relaxed day (Tue/Wed/Thu) — workout optional, lock skipped.",
    )
    if result is not None:
        return result

    result = _check(
        "weekly_minimum_met",
        fired=weekly_minimum_met,
        reason_true="Weekly workout minimum already reached.",
        reason_false="Weekly workout minimum not yet reached.",
        terminal_reason="Weekly workout minimum already met — lock skipped.",
    )
    if result is not None:
        return result

    return _stage(
        fired=True,
        stage="full_lock_pending_heat_check",
        reason=(
            "No skip condition applies. The real locker still checks live "
            "Warsaw temperature before showing the full lock — not "
            "evaluated here." + degraded_note
        ),
        context=stage_context,
    )
