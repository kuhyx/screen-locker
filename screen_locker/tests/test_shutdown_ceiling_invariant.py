"""Doing every task reaches the shutdown ceiling, on every day, in every state.

The invariant behind dropping the weekly banked bonus (2026-10-10): the
ladder's floor is the ceiling minus every rung, so a day on which every earner
in ``earned_time.earners_for(day)`` is done to its full units (the tutor's
four blocks included) must shut down exactly at ``shutdown_ceiling_for(day)``
-- never short of it, and never past it. Checked through screen-locker's own
paths, not a re-implementation: the daily reset's :func:`derive`, and the live
pass (first workout, further workouts, flat gates, counted gate blocks, grace
floor) over :class:`ShutdownMixin` with an in-memory config.

Every gate maturity state is covered: ``first_credits`` omitted (0.5.0
``penalty_from``), empty (every earner on its ``confirmed_on``), never paid
out / missing ledger (``None``), first paid today (penalty not started),
maturing (paid yesterday), mature, and a new tutor beside mature gates.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _gate_bonus, _grace_floor, _shutdown
from screen_locker._earned import ceiling, extra_minutes, first_minutes, is_gate
from screen_locker._earned import registry as registry_for
from screen_locker._gate_bonus import apply_counted_bonus
from screen_locker._shutdown import ShutdownMixin
from screen_locker._shutdown_target import DayInputs, derive

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

_FIRST = date(2026, 10, 10)
_LAST = date(2026, 12, 31)
_DAYS = tuple(_FIRST + timedelta(days=n) for n in range((_LAST - _FIRST).days + 1))
# adjust_shutdown_schedule.sh's RESTORE_CEILING: the helper clamps every
# --restore write to 23:00, so the double does too.
_HELPER_CEILING = 23 * 60
_MORNING = 5 * 60

Credits = dict[str, date | None] | None


def _credits(fill: Callable[[date], date | None] | None) -> Callable[[date], Credits]:
    """A per-day ``first_credits`` map giving every earner ``fill(day)``."""

    def build(day: date) -> Credits:
        if fill is None:
            return None
        return {e.name: fill(day) for e in registry_for(day)}

    return build


def _new_tutor_beside_mature(day: date) -> Credits:
    mature = {e.name: date(2026, 8, 1) for e in registry_for(day)}
    return {**mature, "automation": None}


_MATURITY: Mapping[str, Callable[[date], Credits]] = {
    "penalty_from": _credits(None),
    "confirmed_on": lambda _day: {},
    "never_paid": _credits(lambda _day: None),
    "first_paid_today": _credits(lambda day: day),
    "maturing": _credits(lambda day: day - timedelta(days=1)),
    "mature": _credits(lambda _day: date(2026, 8, 1)),
    "new_tutor": _new_tutor_beside_mature,
}
_CASES = [
    pytest.param(
        name, rest, workouts, first, id=f"{name}-rest{rest}-w{workouts}-{first}"
    )
    for name in _MATURITY
    for rest in (False, True)
    for workouts in (1, 2)
    for first in ("none", "09:00", "22:30")
]


def _at(day: date, hhmm: str) -> float | None:
    if hhmm == "none":
        return None
    hours, minutes = map(int, hhmm.split(":"))
    return datetime.combine(day, time(hours, minutes)).astimezone().timestamp()


def _gates(day: date, *, done: bool) -> dict[str, int | bool | None]:
    """Every gate's answer: all done (full units) or none."""
    return {
        e.name: (e.max_units or True) if done else 0
        for e in registry_for(day)
        if is_gate(e)
    }


def _inputs(day: date, case: tuple[str, bool, int, str], *, done: bool) -> DayInputs:
    name, rest, workouts, first = case
    return DayInputs(
        day=day,
        flat=_gates(day, done=done),
        workout_credits=workouts if done else 0,
        rest_day=rest,
        first_done=_at(day, first) if done else None,
        first_credits=_MATURITY[name](day),
    )


@pytest.mark.parametrize(("maturity", "rest", "workouts", "first"), _CASES)
def test_the_reset_lands_every_all_done_day_on_the_ceiling(
    maturity: str, rest: bool, workouts: int, first: str
) -> None:
    """``derive`` (the daily reset's formula) == ceiling on every day."""
    case = (maturity, rest, workouts, first)
    misses = [
        (day.isoformat(), got, ceiling(day))
        for day in _DAYS
        if (got := derive(_inputs(day, case, done=True)).minutes) != ceiling(day)
    ]
    assert misses == []


class _Host(ShutdownMixin):
    """The real add / absorb / floor paths over an in-memory config."""

    def __init__(self, minutes: int) -> None:
        self.config = (minutes, minutes, _MORNING)

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        return self.config

    def _write_shutdown_config(
        self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = False
    ) -> bool:
        assert restore
        self.config = (
            min(_HELPER_CEILING, mon_wed),
            min(_HELPER_CEILING, thu_sun),
            morning_end,
        )
        return True


def _live_pass(day: date, case: tuple[str, bool, int, str]) -> int:
    """Reset with nothing done, then every credit as the live pass applies it."""
    _, rest, workouts, first = case
    host = _Host(derive(_inputs(day, case, done=False)).minutes)
    first_done = _at(day, first)
    if first_done is not None:
        host._apply_grace_floor(None, first_done=first_done)
    # A rest day's first unit is already in the reset; a real workout on it
    # is a further unit (_workout_credit's rest_paid rule).
    further = workouts if rest else workouts - 1
    if not rest:
        host._adjust_shutdown_time_later()
    extra = extra_minutes(earned_time.WORKOUT, day)
    for _ in range(further if extra else 0):
        host._adjust_shutdown_time_by(extra)
    state: dict[str, Any] = {}
    for gate in (e for e in registry_for(day) if is_gate(e)):
        if gate.kind == "flat":
            host._adjust_shutdown_time_by(first_minutes(gate, day))
            continue
        for units in range(1, (gate.max_units or 1) + 1):
            with patch.object(_gate_bonus, "earned_units", return_value=units):
                apply_counted_bonus(
                    state, host._adjust_shutdown_time_by, gate, day.isoformat()
                )
    return host.config[1]


@pytest.fixture
def frozen_day() -> Iterator[Callable[[date], Any]]:
    """Point every live path's ``today`` at the simulated day."""

    def at_day(day: date) -> Any:
        iso = day.isoformat()
        return patch.multiple(_shutdown, today_str=lambda: iso), patch.multiple(
            _grace_floor, today_str=lambda: iso, sick_on=lambda _d: False
        )

    return at_day


@pytest.mark.parametrize(("maturity", "rest", "workouts", "first"), _CASES)
def test_the_live_pass_lands_every_all_done_day_on_the_ceiling(
    maturity: str,
    rest: bool,
    workouts: int,
    first: str,
    frozen_day: Callable[[date], Any],
) -> None:
    """Reset + every live credit, in registry order == ceiling on every day."""
    case = (maturity, rest, workouts, first)
    misses = []
    for day in _DAYS:
        shutdown_patch, grace_patch = frozen_day(day)
        with shutdown_patch, grace_patch:
            got = _live_pass(day, case)
        _grace_floor.GRACE_STATE_FILE.unlink(missing_ok=True)
        if got != ceiling(day):
            misses.append((day.isoformat(), got, ceiling(day)))
    assert misses == []
