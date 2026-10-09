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

from datetime import date, datetime
import functools
import logging
from pathlib import Path
from typing import Final

import earned_time

from screen_locker._constants import HMAC_KEY_FILE
from screen_locker._day import today_str

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


def registry(day: date | None = None) -> tuple[earned_time.Earner, ...]:
    """The earners in force on ``day`` (default today).

    ``earners_for`` (earned_time >= 0.5) switches the registry on
    ``TUTOR_FROM``; an older earned_time has one static registry.
    """
    fn = getattr(earned_time, "earners_for", None)
    return tuple(earned_time.EARNERS if fn is None else fn(day))


def is_gate(earner: earned_time.Earner) -> bool:
    """A ledger-backed earner whose gate publishes credits (not the workout).

    The workout has a ledger too, but screen-locker writes it and
    ``WorkoutCreditMixin`` applies it.
    """
    return earner.ledger is not None and earner.name != earned_time.WORKOUT.name


def flat_earners(day: date | None = None) -> tuple[earned_time.Earner, ...]:
    """The once-per-day, ledger-backed earners in force on ``day``."""
    return tuple(e for e in registry(day) if e.kind == "flat" and is_gate(e))


def gate_earners(day: date | None = None) -> tuple[earned_time.Earner, ...]:
    """Every gate earner in force on ``day``, flat and counted, in registry order."""
    return tuple(e for e in registry(day) if is_gate(e))


def counted_gate_earners(day: date | None = None) -> tuple[earned_time.Earner, ...]:
    """Gate earners paid per unit on ``day`` (the Automation tutor's blocks)."""
    return tuple(e for e in registry(day) if e.kind == "counted" and is_gate(e))


def watched_earners() -> tuple[earned_time.Earner, ...]:
    """Every gate earner of every registry, so a cutover misses no ledger."""
    fn = getattr(earned_time, "all_earners", None)
    pool = earned_time.EARNERS if fn is None else fn()
    return tuple(e for e in pool if is_gate(e))


def earned_today(
    earner: earned_time.Earner, now: datetime | None = None
) -> bool | None:
    """Whether ``earner``'s gate recorded today's credit; ``None`` if unknown."""
    return earned_time.done_today(earner, ledger_file(earner), HMAC_KEY_FILE, now=now)


def earned_units(earner: earned_time.Earner, day: date) -> int | None:
    """How many of a counted earner's units count for ``day``; ``None`` if unknown."""
    return earned_time.credit_units(earner, ledger_file(earner), HMAC_KEY_FILE, day)


def gate_answers(day: date | None = None) -> dict[str, int | bool | None]:
    """Every gate earner's answer for ``day`` (default today), unknown logged.

    Flat earners answer "done today"; counted ones (the tutor) their units.
    On an earned_time without counted gates this is exactly
    :func:`flat_answers`.
    """
    target = day or datetime.now().astimezone().date()
    answers: dict[str, int | bool | None] = dict(flat_answers())
    for earner in counted_gate_earners(target):
        units = earned_units(earner, target)
        if units is None:
            _warn_unknown(earner)
        answers[earner.name] = units
    return answers


def flat_answers() -> dict[str, bool | None]:
    """Today's answer from every flat earner, an unknown one logged."""
    answers: dict[str, bool | None] = {}
    for earner in flat_earners():
        answer = earned_today(earner)
        if answer is None:
            _warn_unknown(earner)
        answers[earner.name] = answer
    return answers


def _warn_unknown(earner: earned_time.Earner) -> None:
    _logger.warning(
        "%s state could not be checked; no shutdown time for it", earner.label
    )


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


def first_credits(
    earners: tuple[earned_time.Earner, ...], day: date
) -> dict[str, date | None] | None:
    """Each penalised ledger earner's first real credit up to ``day``, for resolve.

    ``earned_time.resolve`` / ``base_for`` take it as ``first_credits=`` (>= 0.6)
    and then start a penalty no earlier than the day after the gate first
    paid out. Keyed by name over ``earners`` -- the registry the answers came
    from, so the two ``automation`` earners (either side of ``TUTOR_FROM``)
    never collide. An earner without ``penalty_from``, a ledger or a matcher
    is left out (``resolve`` falls back to its ``confirmed_on``).

    Returns:
        The map; ``None`` for a day before today -- history keeps the shutdown
        it was enforced at, never re-resolved -- and on an earned_time
        without ``maturity`` (< 0.6, logged), where callers resolve as before.
    """
    if day < date.fromisoformat(today_str()):
        return None
    fn = getattr(earned_time, "maturity", None)
    if fn is None:
        _warn_no_maturity()
        return None
    return {
        e.name: fn(e, ledger_file(e), HMAC_KEY_FILE, day).first_credit
        for e in earners
        if e.penalty_from is not None and e.ledger is not None and e.match is not None
    }


@functools.cache
def _warn_no_maturity() -> None:
    """Once per process: the installed earned_time predates maturity."""
    _logger.warning(
        "earned_time has no maturity (needs >= 0.6); every penalty starts on "
        "its penalty_from, even for a gate that never paid out"
    )
