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
from datetime import datetime, timezone
import json
import logging
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from screen_locker._constants import (
    EARLY_BIRD_END_HOUR,
    EARLY_BIRD_END_MINUTE,
    EARLY_BIRD_START_HOUR,
)
from screen_locker._log_io import load_workout_log
from screen_locker._sick_tracker import is_sick_day as _is_sick_day

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker._sick_tracker import SickHistory

_logger = logging.getLogger(__name__)


def _today_str() -> str:
    """Return today's date as ``YYYY-MM-DD`` in UTC."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class PredicateResult:
    """One evaluated step in a :class:`LockExplanation` trace."""

    name: str
    fired: bool
    reason: str


@dataclass(frozen=True)
class AutoUpgradeOpportunity:
    """Describes whether the real locker would attempt a live auto-upgrade."""

    would_attempt: bool
    via: str  # "early_bird_expired" | "sick_day" | "none"
    reason: str


@dataclass(frozen=True)
class LockExplanation:
    """Read-only reconstruction of what the lock-decision chain would do."""

    fired: bool
    stage: str
    reason: str
    trace: tuple[PredicateResult, ...]
    auto_upgrade: AutoUpgradeOpportunity
    heat_skip_evaluated: bool


_NO_UPGRADE = AutoUpgradeOpportunity(
    would_attempt=False,
    via="none",
    reason="No pending auto-upgrade opportunity.",
)


def is_scheduled_skip_today(
    scheduled_skips_file: Path, *, today: str | None = None
) -> bool:
    """Return True if *today* is listed in *scheduled_skips_file*."""
    if not scheduled_skips_file.exists():
        return False
    try:
        with scheduled_skips_file.open() as f:
            skips = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read scheduled skips from %s: %s — treating today as NOT "
            "a scheduled skip (the lock chain continues)",
            scheduled_skips_file,
            exc,
        )
        return False
    return (today or _today_str()) in skips


def has_logged_today(log_file: Path, *, today: str | None = None) -> bool:
    """Return True if a validly-signed workout is logged for *today*.

    The day may hold multiple workouts; return True if ANY of today's entries
    verifies (or is acceptably unsigned when no HMAC key is configured).
    """
    entries = load_workout_log(log_file).get(today or _today_str(), [])
    if not entries:
        return False
    key_unavailable = compute_entry_hmac({"_probe": True}) is None
    for entry in entries:
        if verify_entry_hmac(entry):
            return True
        if key_unavailable and "hmac" not in entry:
            _logger.info("HMAC key unavailable — accepting unsigned entry")
            return True
    _logger.warning("HMAC verification failed for today's log entries")
    return False


def is_early_bird_pending(pending_file: Path, *, today: str | None = None) -> bool:
    """Return True if today has an unresolved early-bird pending marker."""
    if not pending_file.exists():
        return False
    try:
        with pending_file.open() as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read the early-bird pending marker at %s: %s — treating "
            "it as not pending, so the lock chain proceeds as if no early bird "
            "was claimed today",
            pending_file,
            exc,
        )
        return False
    if not isinstance(state, dict) or state.get("date") != (today or _today_str()):
        return False
    if verify_entry_hmac(state):
        return True
    if compute_entry_hmac({"_probe": True}) is None and "hmac" not in state:
        _logger.info("HMAC key unavailable — accepting unsigned pending marker")
        return True
    _logger.warning("HMAC verification failed for early-bird pending marker")
    return False


def is_sick_day_today(history: SickHistory, *, today: str | None = None) -> bool:
    """Return True if today is recorded as a sick day.

    Thin wrapper around ``_sick_tracker.is_sick_day`` kept here so callers of
    the status layer have one predicate module to import from.
    """
    return _is_sick_day(history, today=today)


def _early_bird_window_open(*, extended: bool, local_minutes: int) -> bool:
    """Deliberate, independent reimplementation of ``_is_early_bird_time``.

    Not shared with ``EarlyBirdMixin._is_early_bird_time`` because too many
    existing tests are pinned to its ``_get_local_time_minutes`` patch point.
    Kept here as a small, separate, pure re-implementation for the status
    layer only — see the module docstring in ``_early_bird.py``.
    """
    start = EARLY_BIRD_START_HOUR * 60
    end = 9 * 60 if extended else EARLY_BIRD_END_HOUR * 60 + EARLY_BIRD_END_MINUTE
    return start <= local_minutes < end


def describe_auto_upgrade_opportunity(
    *,
    early_bird_pending: bool,
    early_bird_window_open: bool,
    is_sick_day: bool,
) -> AutoUpgradeOpportunity:
    """Describe what the real ``_try_auto_upgrade_*`` methods would attempt.

    Read-only stand-in for ``AutoUpgradeMixin._check_today_state_exits``'s
    branching — never calls phone/RunnerUp verification and never writes to
    ``workout_log.json``.
    """
    if early_bird_pending and not early_bird_window_open:
        return AutoUpgradeOpportunity(
            would_attempt=True,
            via="early_bird_expired",
            reason=(
                "Early-bird window closed with no workout logged — the next "
                "lock run will try phone/RunnerUp verification before "
                "falling back to a full lock."
            ),
        )
    if is_sick_day:
        return AutoUpgradeOpportunity(
            would_attempt=True,
            via="sick_day",
            reason=(
                "Sick day logged — the next lock run will try phone/RunnerUp "
                "verification to upgrade it to a real workout."
            ),
        )
    return _NO_UPGRADE


def _stage(
    *,
    fired: bool,
    stage: str,
    reason: str,
    trace: list[PredicateResult],
    auto_upgrade: AutoUpgradeOpportunity,
) -> LockExplanation:
    """Build a terminal :class:`LockExplanation` from the trace so far."""
    return LockExplanation(
        fired=fired,
        stage=stage,
        reason=reason,
        trace=tuple(trace),
        auto_upgrade=auto_upgrade,
        heat_skip_evaluated=False,
    )


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

    auto_upgrade = describe_auto_upgrade_opportunity(
        early_bird_pending=pending,
        early_bird_window_open=window_open,
        is_sick_day=sick_today,
    )

    trace: list[PredicateResult] = []

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
                trace=trace,
                auto_upgrade=auto_upgrade,
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

    result = _check(
        "already_logged",
        fired=logged,
        reason_true="A validly-signed workout is already logged for today.",
        reason_false="No workout logged for today yet.",
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
            "evaluated here."
        ),
        trace=trace,
        auto_upgrade=auto_upgrade,
    )
