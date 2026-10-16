"""Tests for ``_shutdown_target``: the one formula behind reset and preview."""

from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import earned_time
import sickdays

from screen_locker import _grace_floor
from screen_locker._shutdown_base import base_minutes
from screen_locker._shutdown_target import (
    DayInputs,
    day_credit_count,
    derive,
    gather,
    gather_inputs,
    workout_units,
)
from screen_locker.tests._sick_helpers import mark_sick

if TYPE_CHECKING:
    from pathlib import Path

_DAY = date(2026, 10, 10)
_ISO = _DAY.isoformat()
SICK_FLOOR = earned_time.SICK_SHUTDOWN_FLOOR_MINUTES
_FLAT = {"leetcode": False, "reading": False, "anki": False, "tutor": False}


def at(hhmm: str) -> float:
    hours, minutes = map(int, hhmm.split(":"))
    return datetime.combine(_DAY, time(hours, minutes)).astimezone().timestamp()


def log_with(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    log = tmp_path / "log.json"
    log.write_text(json.dumps({_ISO: entries}))
    return log


class TestTarget:
    def test_a_rest_day_stands_in_for_the_first_workout_only(self) -> None:
        assert workout_units(0, rest_day=True) == 1
        assert workout_units(2, rest_day=True) == 2
        assert workout_units(0, rest_day=False) == 0

    def test_the_floor_lifts_and_the_lift_is_reported(self) -> None:
        target = derive(
            DayInputs(_DAY, {**_FLAT, "anki": True}, first_done=at("18:55"))
        )
        assert target.minutes == max(target.earned, 19 * 60 + 55)
        assert target.lift == target.minutes - target.earned

    def test_a_sick_day_has_no_grace_floor_but_the_20_00_one(self) -> None:
        target = derive(DayInputs(_DAY, _FLAT, first_done=at("18:55"), sick_day=True))
        assert target.grace is None
        assert target.resolution.sick is True
        assert target.minutes == max(SICK_FLOOR, target.earned)
        # The lift is the sick floor's, so later credits absorb it first.
        assert target.lift == target.resolution.sick_lift_minutes
        assert target.lift == SICK_FLOOR - target.earned

    def test_a_sick_day_above_20_00_keeps_the_ladder_value(self) -> None:
        busy = dict.fromkeys(_FLAT, True)
        target = derive(DayInputs(_DAY, busy, workout_credits=1, sick_day=True))
        assert target.minutes == target.earned
        assert target.minutes > SICK_FLOOR
        assert target.lift == 0

    def test_gather_keeps_the_sick_floor_when_the_workout_lock_is_kept(self) -> None:
        """Rule 2: the 20:00 floor is the day's, whatever the keep set says."""
        mark_sick(_DAY, keep=[sickdays.LOCKER_WORKOUT])
        assert gather_inputs(_DAY, None).sick_day is True

    def test_base_minutes_keeps_the_sick_floor_when_the_workout_lock_is_kept(
        self,
    ) -> None:
        plain = base_minutes(_DAY)
        assert plain < SICK_FLOOR  # reading's cut is in force on this date
        mark_sick(_DAY, keep=[sickdays.LOCKER_WORKOUT])
        assert base_minutes(_DAY) == SICK_FLOOR

    def test_not_sick_is_the_plain_sum(self) -> None:
        target = derive(DayInputs(_DAY, _FLAT))
        assert target.resolution.sick is False
        assert target.minutes == target.earned == target.resolution.shutdown_minutes

    def test_no_log_counts_no_workouts(self) -> None:
        assert day_credit_count(None, _DAY) == 0

    def test_gather_reads_every_real_source(self, tmp_path: Path) -> None:
        log = log_with(
            tmp_path,
            [
                {
                    "workout_data": {"type": "manual_workout", "end_time": "18:00"},
                    "timestamp": "2026-10-10T20:00:00+00:00",
                }
            ],
        )
        with (
            patch("screen_locker._shutdown_target.gate_answers", return_value=_FLAT),
            patch.object(_grace_floor, "first_credit_time", return_value=None),
        ):
            target = gather(_DAY, log)
        assert target.resolution.term("workout").answer == 1
        assert target.first_done_at == at("18:00")
        assert target.grace == 19 * 60
        assert not target.rest_day
