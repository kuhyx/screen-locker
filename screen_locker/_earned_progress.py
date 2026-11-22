"""A gate's signed progress, read for the shutdown sum (``earned_time`` 0.24.0).

A gate signs "done N of M for day D" in its own ledger; ``earned_time`` pays a
no that share of a yes and owns every other pay rule (``term_for``; none is
priced here). A day with no such row pays by yes/no exactly as before. Two
readers here, one per caller:

* :func:`progress_for` -- the whole day's map, for ``earned_time.resolve``
  (the daily reset, the sick floor and the preview);
* :func:`term_minutes` -- one earner's pay, for the live pass, which has to
  know what it may pay *now* before it subtracts what it already applied.

The workout is left out of the map on purpose: ``WorkoutCreditMixin`` applies
it per unit, so a share paid by the reset alone would be wiped or doubled.
Both look the readers up at call time: an installed ``earned_time`` older than
0.24 pays by yes/no, logged once, never raises.
"""

from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING

import earned_time

from screen_locker import _earned
from screen_locker._gate_off import gate_off

if TYPE_CHECKING:
    from datetime import date

_logger = logging.getLogger(__name__)


@functools.cache
def _warn_no_progress() -> None:
    """Once per process: the installed earned_time predates progress."""
    _logger.warning(
        "earned_time has no progress reader (needs >= 0.24); every bonus pays "
        "all-or-nothing"
    )


def progress_for(day: date) -> dict[str, earned_time.Progress] | None:
    """Each non-workout earner's signed progress on ``day``; ``None`` if none.

    ``None`` for no row at all (so ``resolve`` is called exactly as before)
    and on an ``earned_time`` without ``progress_map``.
    """
    fn = getattr(earned_time, "progress_map", None)
    if fn is None:
        _warn_no_progress()
        return None
    earners = tuple(
        e for e in _earned.registry(day) if e.name != earned_time.WORKOUT.name
    )
    found: dict[str, earned_time.Progress] = fn(
        day,
        _earned.LEDGER_HOME,
        _earned.HMAC_KEY_FILE,
        earners=earners,
        gate_off={e.name for e in earners if gate_off(e, day)},
    )
    return found or None


def term_minutes(earner: earned_time.Earner, day: date, *, answer: bool | None) -> int:
    """The shutdown minutes ``earner`` earned on ``day``, priced by the library.

    ``earned_time.term_for`` owns every rule (a yes pays the rung, a no the
    signed progress's share, ``None`` nothing, the review's dated rule); this
    only reads the fact it needs. Before 0.24 it is the old yes/no.
    """
    term_for = getattr(earned_time, "term_for", None)
    read = getattr(earned_time, "read_progress", None)
    if term_for is None or read is None:
        _warn_no_progress()
        return _earned.first_minutes(earner, day) if answer else 0
    fact = read(
        earner,
        _earned.ledger_file(earner),
        _earned.HMAC_KEY_FILE,
        day,
        gate_off=gate_off(earner, day),
    )
    return int(term_for(earner, day, answer=answer, progress=fact).shutdown_minutes)
