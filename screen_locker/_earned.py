"""Shutdown hours from the shared earner registry (``earned_time``, kuhyx/utils).

Every gate's reward -- the workout, the LeetCode hour, the reading hour and
whatever is registered next -- is defined once in ``earned_time``, which
steam-backlog-enforcer reads for gaming time too. This module is the
screen-locker side of it: where the ledgers live, and how minutes are shown.

The gates publish facts only; none writes the shutdown config. Their ledgers
are HMAC-verified against :data:`HMAC_KEY_FILE` and *fail closed* -- an
unreadable ledger or key earns nothing, and says so.

Minutes end to end: the registry, ``/etc/shutdown-schedule.conf`` (its
``*_MINUTES`` keys) and every shutdown time in this package are minutes after
midnight, so a 30-minute earner is applied exactly.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

import earned_time

from screen_locker._constants import HMAC_KEY_FILE

if TYPE_CHECKING:
    from datetime import date, datetime

_logger: Final = logging.getLogger(__name__)

# Every earner's ``ledger`` is relative to this. Read-only from here; resolved
# at call time so the test suite's redirect (tests/_isolated_state.py) applies.
LEDGER_HOME: Final = Path.home()

_MINUTES_PER_HOUR: Final = 60


def hhmm(minutes: int) -> str:
    """A time of day, given in minutes after midnight, as ``HH:MM``."""
    hours, rest = divmod(minutes, _MINUTES_PER_HOUR)
    return f"{hours:02d}:{rest:02d}"


def span(minutes: int) -> str:
    """A duration in minutes as ``2h``, ``30m`` or ``1h30m``."""
    hours, rest = divmod(minutes, _MINUTES_PER_HOUR)
    if not rest:
        return f"{hours}h"
    if not hours:
        return f"{rest}m"
    return f"{hours}h{rest:02d}m"


def ledger_file(earner: earned_time.Earner) -> Path:
    """Where ``earner``'s gate keeps its ledger."""
    if earner.ledger is None:
        msg = f"earner {earner.name!r} has no ledger"
        raise ValueError(msg)
    return LEDGER_HOME / earner.ledger


def flat_earners() -> tuple[earned_time.Earner, ...]:
    """The once-per-day, ledger-backed earners (the workout is counted here)."""
    return tuple(
        e for e in earned_time.EARNERS if e.kind == "flat" and e.ledger is not None
    )


def earned_today(
    earner: earned_time.Earner, now: datetime | None = None
) -> bool | None:
    """Whether ``earner``'s gate recorded today's credit; ``None`` if unknown."""
    return earned_time.done_today(earner, ledger_file(earner), HMAC_KEY_FILE, now=now)


def flat_answers() -> dict[str, bool | None]:
    """Today's answer from every flat earner, an unknown one logged."""
    answers: dict[str, bool | None] = {}
    for earner in flat_earners():
        answer = earned_today(earner)
        if answer is None:
            _logger.warning(
                "%s state could not be checked; no shutdown time for it",
                earner.label,
            )
        answers[earner.name] = answer
    return answers


# The day-aware ladder API (earned_time >= 0.4, from 2026-10-10). Looked up at
# call time so the installed 0.3.0 -- which has none of it -- still runs, on
# the raw fields it always used.
def first_minutes(earner: earned_time.Earner, day: date) -> int:
    """What ``earner``'s first unit pushes shutdown later by on ``day``."""
    fn = getattr(earned_time, "shutdown_minutes_for", None)
    return earner.shutdown_minutes if fn is None else int(fn(earner, day))


def extra_minutes(earner: earned_time.Earner, day: date) -> int:
    """What each further unit of a counted earner earns on ``day``."""
    fn = getattr(earned_time, "extra_shutdown_minutes_for", None)
    return earner.extra_shutdown_minutes if fn is None else int(fn(earner, day))


def ceiling(day: date) -> int:
    """The latest shutdown ``day`` can earn, minutes after its midnight."""
    fn = getattr(earned_time, "shutdown_ceiling_for", None)
    return earned_time.SHUTDOWN_CEILING_MINUTES if fn is None else int(fn(day))


def first_credit_time(earner: earned_time.Earner, day: date) -> float | None:
    """Unix time of ``earner``'s first verified credit counting for ``day``.

    ``None`` when there is none, when it cannot be checked, and on an
    ``earned_time`` without ``first_credit_at`` (0.3.0) -- logged, because
    then the grace floor sees no ledger earner at all.
    """
    fn = getattr(earned_time, "first_credit_at", None)
    if fn is None:
        _warn_no_first_credit()
        return None
    stamp: float | None = fn(earner, ledger_file(earner), HMAC_KEY_FILE, day)
    return stamp


@functools.cache
def _warn_no_first_credit() -> None:
    """Once per process: the installed earned_time predates first_credit_at."""
    _logger.warning(
        "earned_time has no first_credit_at (needs >= 0.4); the grace floor "
        "sees no ledger earner, only the workout log"
    )
