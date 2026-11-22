"""The workout's signed "progress" row: how far a too-short verified day got.

Writer only. The row is inert today -- no reader in ``earned_time`` looks at
``kind: "progress"`` yet -- and it never touches a bonus, a shutdown time, a
stamp or the web payload. It records ``done`` of ``target`` for one day, in
integers, from the verified RunnerUp TCX only::

    {"kind": "progress", "entry_id": "progress:<day>:<done>:<target>",
     "day": <day>, "amount": 0,
     "detail": {"source": "workout", "for_day": <day>,
                "done": "<digits>", "target": "<digits>"}}

The larger of the two fractions (distance / distance bar, moving time / time
bar) is the one recorded, so ``done``/``target`` is metres over metres or
seconds over seconds. The bars come from ``_constants`` and appear only inside
the signed row: they are never logged or shown (the constants file keeps a
deliberate leeway hidden). The ADVERTISED bars are the targets, not the
looser accept bars, so a row never reveals the leeway.

Signing, locking and idempotence on ``entry_id`` are the credit rows' own
(:func:`screen_locker._workout_ledger.append_rows`); a second short run the
same day has a larger ``done`` and so a new id.
"""

from __future__ import annotations

import logging
from typing import Any

from screen_locker._constants import MIN_RUN_DISTANCE_KM, MIN_WORKOUT_DURATION_MINUTES
from screen_locker._workout_ledger import append_rows

_logger = logging.getLogger(__name__)

SOURCE = "workout"


def progress_pair(metres: float, moving_seconds: float) -> tuple[int, int] | None:
    """``(done, target)`` of the leading fraction, or ``None`` with nothing done.

    Both fractions are compared exactly, by cross-multiplying integers; a tie
    goes to distance. ``done`` is floored and capped at its ``target``.
    """
    distance_target = round(MIN_RUN_DISTANCE_KM * 1000)
    time_target = MIN_WORKOUT_DURATION_MINUTES * 60
    distance_done = min(int(max(metres, 0.0)), distance_target)
    time_done = min(int(max(moving_seconds, 0.0)), time_target)
    if distance_done * time_target >= time_done * distance_target:
        done, target = distance_done, distance_target
    else:
        done, target = time_done, time_target
    return (done, target) if done > 0 else None


def progress_row(for_day: str, done: int, target: int) -> dict[str, Any] | None:
    """The unsigned progress row; ``None`` when nothing was done."""
    if done <= 0:
        return None
    return {
        "kind": "progress",
        "entry_id": f"progress:{for_day}:{done}:{target}",
        "day": for_day,
        "amount": 0,
        "detail": {
            "source": SOURCE,
            "for_day": for_day,
            "done": str(done),
            "target": str(target),
        },
    }


def record_progress(for_day: str, metres: float, moving_seconds: float) -> None:
    """Append the day's progress row; never raises, never changes a verdict.

    Call only for a day verified from RunnerUp TCX data and judged too short.
    A row that cannot be signed or written is logged at warning or above by
    ``append_rows``; any other failure is logged here.
    """
    try:
        pair = progress_pair(metres, moving_seconds)
        row = progress_row(for_day, *pair) if pair is not None else None
        if row is not None:
            append_rows([row])
    except Exception:  # pylint: disable=broad-exception-caught  # a progress row must never change the verdict
        _logger.exception(
            "Could not write the progress row for %s; the workout verdict is unchanged",
            for_day,
        )
