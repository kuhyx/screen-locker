"""The one thing the enforce path must never do: lock over a logged workout.

Every skip in ``_startup_checks._check_non_verify_exits`` is a rung of a
first-match-wins ladder, and the ladder's ORDER is what decides whether a
logged workout counts. That order has been wrong before: on 2026-09-18 an
expired early-bird marker sat one rung above ``workout_logged_today``, so a
walk logged on the lock screen at 09:32 closed the lock and the 09:35 tick
locked again -- and would have every five minutes for the rest of the day.
The DECISION line even printed ``also=workout_logged_today``; the evidence
was there, only the gate was missing.

This module is that gate. It runs right before the ``enforced`` decision is
recorded and refuses to build a lock screen when a counted workout for today
is already in the log, whatever the ladder above it concluded. Reaching it
with a workout logged is a bug in the ladder, so it is reported at ERROR --
the locker must fail safe (no lock) and say so, not fail closed on the user.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


_logger = logging.getLogger(__name__)

GUARD_REASON = "workout_logged_today_guard"
GUARD_DETAIL = (
    "A counted workout is already logged today but the exemption ladder fell "
    "through to enforcement — refusing to lock (ladder bug, see journal ERROR)."
)


def refuse_to_lock_over_logged_workout(
    has_logged_today: Callable[[], bool],
    record_skip: Callable[[str, str], None],
) -> bool:
    """Skip enforcement if today already holds a counted workout.

    Takes the locker's two relevant methods rather than the locker itself so
    the guard stays a pure function of "is there a workout?" and "how do I
    skip?". Returns True when the guard fired (the skip was recorded through
    *record_skip*, which exits the process), False when the lock may go
    ahead. The ERROR is deliberate: a fired guard means a rung above it is
    misordered, and that has to be visible in the journal rather than quietly
    absorbed as one more skip.
    """
    if not has_logged_today():
        return False
    _logger.error(
        "Enforcement reached with a workout already logged today — the "
        "early-exit ladder in _startup_checks/_auto_upgrade is misordered. "
        "Refusing to lock; fix the ladder so workout_logged_today is reached."
    )
    record_skip(GUARD_REASON, GUARD_DETAIL)
    return True
