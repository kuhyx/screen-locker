"""Grace floor: shutdown is never earlier than the day's first task + 60 min.

Someone who gets home at 18:10 and finishes their first task at 18:55 is not
cut off at 19:00. The floor is ``first done + GRACE_MINUTES``, capped at the
day's ceiling. "First done" is the earliest of every ledger earner's first
verified credit (``earned_time.first_credit_at``) and the workout's own
completion time -- the end of the run or walk, never the moment a sync
happened to log it, so a late upload does not move the floor later.

**A floor, not a bonus.** The config is otherwise read-add-write: every
earner adds its minutes to whatever is there. Lifting it to the floor and
then letting the next earner add on top would pay the lift twice (anki at
21:00 lifts to 22:00; reading then makes 22:30 where max(earned, floor) is
22:00). So the lift is remembered for the day in ``grace_floor.json`` and
later additions are paid out of it first: with ``E`` earned, floor ``G`` and
lift ``L = max(0, G - E)``, adding ``m`` moves the config by
``max(0, m - L)`` and leaves ``L' = max(0, L - m)`` -- which keeps the config
at ``max(E + m, G)`` without ever needing to know ``E``.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
from typing import TYPE_CHECKING

import earned_time

from screen_locker._bonus_lock import bonus_lock
from screen_locker._constants import GRACE_MINUTES, GRACE_STATE_FILE
from screen_locker._day import today_str
from screen_locker._earned import ceiling, first_credit_time, flat_earners, hhmm
from screen_locker._log_io import load_workout_log
from screen_locker._rest_day import is_rest_day
from screen_locker._sick_tracker import is_sick_day, load_history
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
    """The earliest moment any earner was done on ``day``; ``None`` if none."""
    times = [first_credit_time(e, day) for e in flat_earners()]
    times.append(_workout_time(day, log_file, rest_day=rest_day))
    on_day = [
        t
        for t in times
        if t is not None and datetime.fromtimestamp(t).astimezone().date() == day
    ]
    return min(on_day, default=None)


def sick_on(day: date) -> bool:
    """Whether ``day`` is a sick day, from the sick-day history itself.

    On a sick day the sick-day shutdown wins and there is no grace floor (the
    user's call, 2026-10-09): the floor would otherwise lift the sick-day
    reduction straight back up.
    """
    return is_sick_day(load_history(), today=day.isoformat())


def grace_for(first_done: float | None, day: date) -> int | None:
    """The floor for ``day`` in minutes after midnight, or ``None`` if none."""
    if first_done is None:
        return None
    moment = datetime.fromtimestamp(first_done).astimezone()
    if moment.date() != day:
        return None
    done = moment.hour * 60 + moment.minute
    return min(ceiling(day), done + GRACE_MINUTES)


def _load_lift(state_file: Path, today: str) -> int:
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
    lift = _load_lift(state_file or GRACE_STATE_FILE, today_str())
    return max(0, minutes - lift), max(0, lift - minutes)


def tonight_minutes(config: tuple[int, int, int], day: date) -> int:
    """``day``'s shutdown from a (mon_wed, thu_sun, morning_end) config."""
    mon_wed, thu_sun, _ = config
    return mon_wed if day.weekday() in _MON_WED else thu_sun


class GraceFloorMixin:
    """Lifts tonight's shutdown to the grace floor; composed into ShutdownMixin."""

    if TYPE_CHECKING:

        def _read_shutdown_config(self) -> tuple[int, int, int] | None: ...

        def _write_shutdown_config(
            self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = ...
        ) -> bool: ...

    def _apply_grace_floor(
        self, log_file: Path | None, *, first_done: float | None = None
    ) -> bool:
        """Lift tonight's shutdown to the grace floor if it sits below it.

        ``first_done`` overrides the ledgers' answer (the preview script's
        simulations). Returns True when the config was raised on this call.
        """
        day = date.fromisoformat(today_str())
        if sick_on(day):
            _logger.info("Grace floor: skipped, today is a sick day")
            return False
        if first_done is None:
            first_done = first_done_at(day, log_file, rest_day=is_rest_day(day))
        floor = grace_for(first_done, day)
        if floor is None:
            return False
        with bonus_lock(GRACE_STATE_FILE):
            config = self._read_shutdown_config()
            if config is None:
                _logger.warning("Grace floor: shutdown config unreadable; not applied")
                return False
            current = tonight_minutes(config, day)
            if current >= floor:
                return False
            mon_wed, thu_sun, morning = config
            if not self._write_shutdown_config(
                max(mon_wed, floor), max(thu_sun, floor), morning, restore=True
            ):
                _logger.warning("Grace floor: failed to write shutdown config")
                return False
            lift = _load_lift(GRACE_STATE_FILE, today_str()) + floor - current
            save_lift(lift, GRACE_STATE_FILE)
        _logger.info(
            "Grace floor: shutdown %s -> %s (first task done + %d min).",
            hhmm(current),
            hhmm(floor),
            GRACE_MINUTES,
        )
        return True
