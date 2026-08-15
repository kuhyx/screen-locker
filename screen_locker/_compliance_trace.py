"""Trace dataclasses and auto-upgrade description for the lock explanation.

Split out of :mod:`screen_locker._compliance_state` to keep every file under
the 250-line cap. Re-exported from there, so existing imports and patch
targets for the predicate functions are unchanged.

Nothing here touches ADB, sudo, subprocess, the network or the disk.
"""

from __future__ import annotations

from dataclasses import dataclass


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
