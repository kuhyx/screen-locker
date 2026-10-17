"""When the day's first task was done, and the day's floor lift.

The grace floor (first task + 60 min) is gone since 2026-10-17: a credit at
or after tonight's shutdown now counts from its own time
(:mod:`screen_locker._late_credit`), which is what the floor approximated,
and the floor's lift then absorbed minutes the late credit had already
restarted from (LeetCode late at 19:00, reading at 19:30: 20:10, not 20:20).

What stays: :func:`first_done_at` (shown by the preview and the reset log)
and the lift file. The lift is ``0`` on every day now (no floor lifts the
config above the earned sum), but ``plan_absorb`` still spends a stale one
recorded before the change, once.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
from typing import TYPE_CHECKING

import earned_time

from screen_locker._constants import GRACE_STATE_FILE
from screen_locker._day import today_str
from screen_locker._earned import first_credit_time, gate_earners
from screen_locker._log_io import load_workout_log
from screen_locker._weekly_check import credit_key, day_workout_index
from screen_locker._workout_ledger import entry_done_at

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_MON_WED = frozenset({0, 1, 2})


def workout_done_at(log_file: Path, day: date) -> float | None:
    """The completion time of ``day``'s first counted workout, if any."""
    iso = day.isoformat()
    entries = [
        e for e in load_workout_log(log_file).get(iso, []) if isinstance(e, dict)
    ]
    siblings = day_workout_index(entries)
    times = [
        stamp
        for index, entry in enumerate(entries)
        if credit_key(iso, index, entry, siblings) is not None
        and (stamp := entry_done_at(entry, day)) is not None
    ]
    return min(times, default=None)


def _workout_time(day: date, log_file: Path | None, *, rest_day: bool) -> float | None:
    """When ``day``'s first workout was done: the ledger's and the log's view.

    The workout ledger (``earned_time`` >= 0.4) holds only RunnerUp and rest
    days, so the log still answers for manual and StrongLifts workouts. On a
    rest day the ledger is skipped: its rest row is stamped at the day's
    midnight, which is not a completion and would otherwise erase the floor.
    """
    times: list[float | None] = []
    if log_file is not None:
        times.append(workout_done_at(log_file, day))
    if not rest_day and earned_time.WORKOUT.ledger is not None:
        times.append(first_credit_time(earned_time.WORKOUT, day))
    return min((t for t in times if t is not None), default=None)


def first_done_at(
    day: date, log_file: Path | None, *, rest_day: bool = False
) -> float | None:
    """The earliest moment any earner was done on ``day``; ``None`` if none.

    Every gate in force on ``day`` counts, flat or counted: the Automation
    tutor's first verified block starts the floor like a LeetCode solve does.
    """
    times = [first_credit_time(e, day) for e in gate_earners(day)]
    times.append(_workout_time(day, log_file, rest_day=rest_day))
    on_day = [
        t
        for t in times
        if t is not None and datetime.fromtimestamp(t).astimezone().date() == day
    ]
    return min(on_day, default=None)


def load_lift(state_file: Path, today: str) -> int:
    """Today's recorded floor lift (grace or sick), 0 when none or unreadable."""
    if not state_file.exists():
        return 0  # no lift recorded yet: nothing to absorb
    try:
        raw = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning(
            "Grace state %s unreadable (%s); lift taken as 0", state_file, exc
        )
        return 0
    if not isinstance(raw, dict) or raw.get("date") != today:
        return 0
    return max(0, int(raw.get("lift", 0)))


def save_lift(lift: int, state_file: Path | None = None) -> None:
    """Record how far the floor lifts today's shutdown above the earned time."""
    state_file = state_file or GRACE_STATE_FILE
    payload = {"date": today_str(), "lift": max(0, lift)}
    try:
        state_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        _logger.warning("Could not record the grace lift in %s (%s)", state_file, exc)


def plan_absorb(minutes: int, state_file: Path | None = None) -> tuple[int, int]:
    """How much of an ``minutes`` addition moves the config, and the lift left.

    Commit the lift with :func:`save_lift` only once the write succeeded.
    """
    lift = load_lift(state_file or GRACE_STATE_FILE, today_str())
    return max(0, minutes - lift), max(0, lift - minutes)


def tonight_minutes(config: tuple[int, int, int], day: date) -> int:
    """``day``'s shutdown from a (mon_wed, thu_sun, morning_end) config."""
    mon_wed, thu_sun, _ = config
    return mon_wed if day.weekday() in _MON_WED else thu_sun
