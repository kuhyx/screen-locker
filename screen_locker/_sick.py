"""The one place screen-locker asks the shared ``sickdays`` pool.

A sick day is a date in that pool, nothing else: no budget, no countdown, no
justification and no debt. Every consumer here (lock ladder, shutdown,
status, MCP) goes through this module, so the answer cannot drift between
them and tests have one seam.

Reading never raises: an unreadable pool is logged by ``sickdays`` and reads
as *not sick* -- fail closed, the locks apply.

Two questions, deliberately not one: a sick day may *keep* some lockers active
(``sickdays`` 0.2.0), so

* :func:`stands_down_workout` -- "is the workout lock off?" -- is sick AND the
  workout locker not kept. The lock ladder, its explanation, the status view
  and the missed-alarm penalty's penalised day ask this.
* :func:`is_sick` -- "is the day sick at all?" -- feeds only the 20:00
  shutdown floor, which applies on every sick day whatever it keeps.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
from typing import TYPE_CHECKING

import sickdays

if TYPE_CHECKING:
    from datetime import date

_logger = logging.getLogger(__name__)


def is_sick(day: date | None = None) -> bool:
    """Whether ``day`` (default: today) is a sick day."""
    return sickdays.is_sick_day(day)


def stands_down(locker: str, day: date | None = None) -> bool:
    """Whether ``locker`` (a ``sickdays.LOCKER_*``) is off on ``day``.

    For the few consumers that judge a date by a locker other than the workout
    one (the missed-alarm penalty's ring day is the alarm switch's).
    """
    return sickdays.stands_down(locker, day)


def stands_down_workout(day: date | None = None) -> bool:
    """Whether the workout lock is off on ``day`` (default: today).

    True iff the day is sick and does not keep ``sickdays.LOCKER_WORKOUT``.
    A kept workout lock behaves exactly as on a normal day.
    """
    return stands_down(sickdays.LOCKER_WORKOUT, day)


def sick_dates() -> frozenset[date]:
    """Every date the pool marks sick, past and future."""
    return sickdays.sick_days()


def workout_standdown_dates() -> frozenset[date]:
    """Every sick date on which the workout lock is off (keep-aware)."""
    return frozenset(d for d in sickdays.sick_days() if stands_down_workout(d))


def push_in_background() -> threading.Thread:
    """Start one best-effort ``sickdays.sync_quietly`` on a background thread.

    So the phone sees a lock-screen mark without waiting for the 15-minute
    sickdays-sync timer. Not a daemon: the lock window closes at once and the
    process lingers only until the push ends, instead of killing it mid-write.
    ``sync_quietly`` never raises; a failed push is retried by that timer.
    """
    worker = threading.Thread(
        target=sickdays.sync_quietly, name="sickdays-push", daemon=False
    )
    worker.start()
    return worker


@dataclass(frozen=True)
class MarkResult:
    """Outcome of :func:`mark_today_sick`.

    Attributes:
        ok: Today is a sick day now (newly marked or already was).
        message: What to show the user: a confirmation, or why it was refused.
    """

    ok: bool
    message: str


def mark_today_sick() -> MarkResult:
    """Mark today sick in the shared pool; every gate stands down for it.

    The one tap is ALL-OFF. Already sick counts as success; if that sick day
    keeps some lockers, the keep set is cleared so every locker stands down,
    and a failure to clear it is a refusal (the lock stays up). Any other
    refusal (a free day, an unreadable pool, freedays not importable) is
    returned with sickdays' own explanation, so the lock screen can show it
    instead of unlocking.
    """
    today = sickdays.today()
    try:
        sickdays.add_sick_day(today)
    except sickdays.AlreadySickError:
        if not sickdays.kept_lockers(today):
            _logger.warning("%s was already a sick day; unlocking", today)
            return MarkResult(ok=True, message="Today is already a sick day.")
        return _clear_kept_lockers(today)
    except sickdays.SickDayError as exc:
        _logger.warning("Could not mark %s as a sick day: %s", today, exc)
        return MarkResult(ok=False, message=str(exc))
    _logger.warning("Marked %s as a sick day from the lock screen", today)
    return MarkResult(ok=True, message="Today is a sick day. Get well soon.")


def _clear_kept_lockers(today: date) -> MarkResult:
    """Clear the keep set of an already-sick ``today`` so every locker stands down."""
    try:
        sickdays.set_kept_lockers(today, ())
    except sickdays.SickDayError as exc:
        _logger.warning("Could not clear the kept lockers of %s: %s", today, exc)
        return MarkResult(ok=False, message=str(exc))
    _logger.warning("%s was already a sick day; cleared its kept lockers", today)
    return MarkResult(
        ok=True,
        message="Today was already a sick day; every locker now stands down.",
    )
