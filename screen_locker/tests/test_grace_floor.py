"""Tests for when the day started and the lift bookkeeping (the floor is gone)."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta
import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time

from screen_locker import _grace_floor
from screen_locker._grace_floor import (
    first_done_at,
    plan_absorb,
    save_lift,
    workout_done_at,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_DAY = date(2026, 10, 10)
_ISO = _DAY.isoformat()
_FLAT = {"leetcode": False, "reading": False, "anki": False, "tutor": False}


def at(hhmm: str, day: date = _DAY) -> float:
    hours, minutes = map(int, hhmm.split(":"))
    return datetime.combine(day, time(hours, minutes)).astimezone().timestamp()


def log_with(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    log = tmp_path / "log.json"
    log.write_text(json.dumps({_ISO: entries}))
    return log


class TestWhenTheDayStarted:
    def test_the_first_counted_workout_by_its_own_end(self, tmp_path: Path) -> None:
        log = log_with(
            tmp_path,
            [
                {"workout_data": {"type": "relaxed_day_skip"}, "timestamp": "x"},
                {"workout_data": {"type": "manual_workout", "end_time": "18:40"}},
                {
                    "workout_data": {
                        "type": "runnerup_verified",
                        "completed_at": at("17:00"),
                    }
                },
            ],
        )
        assert workout_done_at(log, _DAY) == at("17:00")

    def test_no_workout_is_none(self, tmp_path: Path) -> None:
        assert workout_done_at(log_with(tmp_path, []), _DAY) is None

    def test_the_earliest_earner_on_the_day_wins(self, tmp_path: Path) -> None:
        log = log_with(
            tmp_path,
            [{"workout_data": {"type": "manual_workout", "end_time": "19:30"}}],
        )
        times = {"reading": at("18:55"), "leetcode": at("23:00", _DAY - timedelta(1))}
        with patch.object(
            _grace_floor,
            "first_credit_time",
            side_effect=lambda e, _d: times.get(e.name),
        ):
            assert first_done_at(_DAY, log) == at("18:55")
            assert first_done_at(_DAY, None) == at("18:55")

    def test_a_rest_day_skips_the_workout_ledger(self) -> None:
        """Its rest row is stamped at midnight, which is not a completion."""
        ledgered = dataclasses.replace(earned_time.WORKOUT, ledger="w.json")
        with (
            patch.object(earned_time, "WORKOUT", ledgered),
            patch.object(_grace_floor, "first_credit_time", return_value=at("00:00")),
        ):
            assert first_done_at(_DAY, None) == at("00:00")
            with patch.object(_grace_floor, "gate_earners", return_value=()):
                assert first_done_at(_DAY, None, rest_day=True) is None

    def test_without_a_workout_ledger_only_the_log_answers(self) -> None:
        bare = earned_time.Earner(
            name="workout", label="workout", gaming_minutes=0, shutdown_minutes=0
        )
        with (
            patch.object(earned_time, "WORKOUT", bare),
            patch.object(_grace_floor, "first_credit_time", return_value=None),
        ):
            assert first_done_at(_DAY, None) is None


class TestLift:
    def test_absorb_pays_from_the_lift_first(self) -> None:
        with patch.object(_grace_floor, "today_str", return_value=_ISO):
            assert plan_absorb(30) == (30, 0)
            save_lift(45)
            assert plan_absorb(30) == (0, 15)
            assert plan_absorb(60) == (15, 0)

    def test_yesterdays_lift_is_spent(self) -> None:
        with patch.object(_grace_floor, "today_str", return_value="2026-10-09"):
            save_lift(45)
        with patch.object(_grace_floor, "today_str", return_value=_ISO):
            assert plan_absorb(30) == (30, 0)

    def test_an_unreadable_state_is_no_lift(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _grace_floor.GRACE_STATE_FILE.write_text("{bad")
        with caplog.at_level(logging.WARNING):
            assert plan_absorb(10) == (10, 0)
        assert "unreadable" in caplog.text

    def test_a_failed_save_is_logged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            save_lift(5, tmp_path / "missing-dir" / "g.json")
        assert "Could not record the grace lift" in caplog.text
