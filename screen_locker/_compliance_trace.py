"""Trace dataclasses and auto-upgrade description for the lock explanation.

Split out of :mod:`screen_locker._compliance_state` to keep every file under
the 250-line cap. Re-exported from there, so existing imports and patch
targets for the predicate functions are unchanged.

Nothing here touches ADB, sudo, subprocess, the network or the disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from screen_locker._sync_client import DegradedSource


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
    # True when a workout backend could not be read on this run, so "no
    # workout logged" is an absence of evidence rather than evidence of
    # absence. Defaulted so every existing construction site stays valid.
    sources_degraded: bool = False


_NO_UPGRADE = AutoUpgradeOpportunity(
    would_attempt=False,
    via="none",
    reason="No pending auto-upgrade opportunity.",
)


def describe_auto_upgrade_opportunity(
    *,
    early_bird_pending: bool,
    early_bird_window_open: bool,
    is_sick_day: bool,
) -> AutoUpgradeOpportunity:
    """Describe what the real ``_try_auto_upgrade_*`` methods would attempt.

    Read-only stand-in for ``AutoUpgradeMixin._check_today_state_exits``'s
    branching — never calls phone/RunnerUp verification and never writes to
    ``log.json``.
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


def describe_degraded_sources(sources: Sequence[DegradedSource]) -> str:
    """Return a clause naming the backends that could not be read, or "".

    "No workout logged" is only trustworthy when every backend answered. On
    2026-08-24 Firebase was unreadable and the phone had already stopped
    writing to the GitHub mirror, so an empty log was reported as though the
    user had simply not trained -- and a screen was locked after a two-hour
    session. Naming the dark source turns that verdict into a question.
    """
    if not sources:
        return ""
    named = ", ".join(f"{src.name} ({src.reason})" for src in sources)
    return (
        f" Could not read: {named} — a workout logged there would be "
        "invisible here, so this is 'unverified', not 'no workout'."
    )


@dataclass(frozen=True)
class StageContext:
    """The parts of a terminal stage that outlive a single predicate.

    Bundled into one object rather than passed as loose keywords: the trace
    and the two run-wide flags travel together through every call site, and
    threading them separately pushed ``_stage`` past the argument limit.
    """

    trace: list[PredicateResult]
    auto_upgrade: AutoUpgradeOpportunity
    sources_degraded: bool = False


def _stage(
    *,
    fired: bool,
    stage: str,
    reason: str,
    context: StageContext,
) -> LockExplanation:
    """Build a terminal :class:`LockExplanation` from the trace so far."""
    return LockExplanation(
        fired=fired,
        stage=stage,
        reason=reason,
        trace=tuple(context.trace),
        auto_upgrade=context.auto_upgrade,
        heat_skip_evaluated=False,
        sources_degraded=context.sources_degraded,
    )
