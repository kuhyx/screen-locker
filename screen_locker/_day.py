"""The one definition of "what day is it" for every day-keyed file.

``log.json``, ``sick_day_state.json``, ``early_bird_pending.json``,
``wake_state.json`` and the sick history are all keyed by ``YYYY-MM-DD``.
Until 2026-09-13 each writer and reader derived that key on its own, and
most of them used ``datetime.now(tz=UTC)`` while the lock window, the phone
app, RunnerUp verification and the status window used LOCAL time. In CEST
that is a two-hour window after local midnight in which a workout logged
"today" was filed under yesterday — the lock check then looked for today,
found nothing, and locked the PC for a workout that was on disk.

The day is the **local calendar day**: it is what the user sees on the
clock when they log, what the lock screen names when it says "no workout
for today", and what the phone already writes. Every module goes through
:func:`today_str` so the two can never disagree again; tests freeze the
clock by patching ``screen_locker._day.datetime``.
"""

from __future__ import annotations

from datetime import UTC, datetime


def today_str(now: datetime | None = None) -> str:
    """Return the local calendar day of *now* (default: this instant) as ``YYYY-MM-DD``.

    *now* may be in any timezone; it is converted to the machine's local zone
    first, which is the only conversion that turns ``22:02Z`` on the 12th
    into the 13th the user actually logged on.
    """
    instant = now if now is not None else datetime.now(tz=UTC)
    return instant.astimezone().strftime("%Y-%m-%d")
