"""Tests for ``_shutdown_target``: the one formula behind reset and preview."""

from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker import _grace_floor
from screen_locker._shutdown_target import (
    DayInputs,
    day_credit_count,
    derive,
    gather,
    workout_units,
)

if TYPE_CHECKING:
    from pathlib import Path

_DAY = date(2026, 10, 10)
_ISO = _DAY.isoformat()
_FLAT = {"leetcode": False, "reading": False, "anki": False, "automation": False}


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

    def test_a_sick_day_drops_the_floor(self) -> None:
        target = derive(DayInputs(_DAY, _FLAT, first_done=at("18:55"), sick_day=True))
        assert target.grace is None
        assert target.minutes == target.earned

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
            patch("screen_locker._shutdown_target.flat_answers", return_value=_FLAT),
            patch.object(_grace_floor, "first_credit_time", return_value=None),
        ):
            target = gather(_DAY, log)
        assert target.resolution.term("workout").answer == 1
        assert target.first_done_at == at("18:00")
        assert target.grace == 19 * 60
        assert not target.rest_day
