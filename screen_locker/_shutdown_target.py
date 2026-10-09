"""Tonight's shutdown, derived from scratch: earned time, rest day, grace floor.

:func:`derive` is pure, and is the one formula behind both the daily reset
(:mod:`screen_locker._shutdown_base`) and the read-only preview
(``scripts/preview_shutdown.py``), so a dry run exercises the real sum::

    earned = earned_time.resolve(answers)          # base + every earner, capped
    target = min(ceiling, max(earned, grace floor))

A declared rest day answers the workout with at least one unit, i.e. its
first-unit bonus; a real workout on top of it earns only what a further unit
earns. :func:`gather` reads today's real inputs; it writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import earned_time

from screen_locker._earned import ceiling, first_credits, gate_answers, registry
from screen_locker._grace_floor import first_done_at, grace_for, sick_on
from screen_locker._log_io import load_workout_log
from screen_locker._rest_day import is_rest_day
from screen_locker._weekly_check import count_day_credits

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date
    from pathlib import Path


@dataclass(frozen=True)
class Target:
    """One day's derived shutdown and what made it.

    Attributes:
        resolution: ``earned_time``'s sum (base + terms, capped).
        rest_day: Whether the day is a declared rest day.
        first_done_at: Unix time the day's first earner was done, if any.
        grace: The grace floor in minutes, or ``None``.
        minutes: The shutdown to write, minutes after midnight.
    """

    resolution: earned_time.Resolution
    rest_day: bool
    first_done_at: float | None
    grace: int | None
    minutes: int

    @property
    def earned(self) -> int:
        """The earned shutdown, before the grace floor."""
        return self.resolution.shutdown_minutes

    @property
    def lift(self) -> int:
        """How far the grace floor lifts the earned shutdown."""
        return self.minutes - self.earned


def workout_units(count: int, *, rest_day: bool) -> int:
    """A rest day stands in for the first workout, never for a further one."""
    return max(count, 1) if rest_day else count


@dataclass(frozen=True)
class DayInputs:
    """Everything one day's shutdown is derived from.

    Attributes:
        day: The day.
        flat: Each gate earner's answer: done (flat) or units (counted, the
            tutor); ``None`` = could not check.
        workout_credits: The log's distinct workout credits.
        rest_day: Declared rest day.
        first_done: Unix time the day's first earner was done, if any.
        sick_day: Sick day: the sick-day shutdown wins, no grace floor.
        first_credits: Each penalised gate's first real credit
            (:func:`~screen_locker._earned.first_credits`); ``None`` resolves
            on ``penalty_from`` alone, as before earned_time 0.6.
    """

    day: date
    flat: Mapping[str, int | bool | None]
    workout_credits: int = 0
    rest_day: bool = False
    first_done: float | None = None
    sick_day: bool = False
    first_credits: Mapping[str, date | None] | None = None


def derive(inputs: DayInputs) -> Target:
    """The pure formula: earned time, then the grace floor, then the ceiling."""
    day = inputs.day
    answers: dict[str, int | bool | None] = dict(inputs.flat)
    answers[earned_time.WORKOUT.name] = workout_units(
        inputs.workout_credits, rest_day=inputs.rest_day
    )
    # The registry is passed explicitly: gate_answers iterated this same
    # day's registry, so the earners asked and the earners summed match.
    earners = registry(day)
    starts = inputs.first_credits
    resolution = (
        earned_time.resolve(answers, day, earners)
        if starts is None
        else earned_time.resolve(answers, day, earners, first_credits=starts)
    )
    grace = None if inputs.sick_day else grace_for(inputs.first_done, day)
    minutes = resolution.shutdown_minutes
    if grace is not None:
        minutes = min(ceiling(day), max(minutes, grace))
    return Target(
        resolution=resolution,
        rest_day=inputs.rest_day,
        first_done_at=inputs.first_done,
        grace=grace,
        minutes=minutes,
    )


def day_credit_count(log_file: Path | None, day: date) -> int:
    """How many distinct workouts ``day``'s log counts (0 without a log)."""
    if log_file is None:
        return 0
    iso = day.isoformat()
    entries = load_workout_log(log_file).get(iso, [])
    return count_day_credits(iso, [e for e in entries if isinstance(e, dict)])


def gather(day: date, log_file: Path | None) -> Target:
    """Derive ``day``'s target from the real ledgers, log and rest days."""
    rest_day = is_rest_day(day)
    return derive(
        DayInputs(
            day=day,
            flat=gate_answers(day),
            workout_credits=day_credit_count(log_file, day),
            rest_day=rest_day,
            first_done=first_done_at(day, log_file, rest_day=rest_day),
            sick_day=sick_on(day),
            first_credits=first_credits(registry(day), day),
        )
    )
