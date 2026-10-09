"""Tests for the grace floor, its lift bookkeeping and the derived target."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta
import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _earned, _grace_floor, _sick_tracker
from screen_locker._grace_floor import (
    GraceFloorMixin,
    first_done_at,
    grace_for,
    plan_absorb,
    save_lift,
    sick_on,
    workout_done_at,
)

if TYPE_CHECKING:
    from pathlib import Path

_DAY = date(2026, 10, 10)
_ISO = _DAY.isoformat()
_FLAT = {"leetcode": False, "reading": False, "anki": False, "automation": False}


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
            with patch.object(_grace_floor, "flat_earners", return_value=()):
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


class TestGraceFor:
    def test_an_hour_after_the_first_task(self) -> None:
        assert grace_for(at("18:55"), _DAY) == 19 * 60 + 55

    def test_capped_at_the_ceiling(self) -> None:
        assert grace_for(at("22:40"), _DAY) == _earned.ceiling(_DAY)

    def test_nothing_done_or_another_day_is_no_floor(self) -> None:
        assert grace_for(None, _DAY) is None
        assert grace_for(at("12:00", _DAY - timedelta(1)), _DAY) is None


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


class Host(GraceFloorMixin):
    """The mixin over an in-memory config."""

    def __init__(self, config: tuple[int, int, int] | None, *, ok: bool = True) -> None:
        self.config = config
        self.ok = ok

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        return self.config

    def _write_shutdown_config(
        self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = False
    ) -> bool:
        assert restore
        if self.ok:
            self.config = (mon_wed, thu_sun, morning_end)
        return self.ok


@pytest.fixture
def saturday() -> Any:
    with patch.object(_grace_floor, "today_str", return_value=_ISO):
        yield


@pytest.mark.usefixtures("saturday")
class TestApply:
    def test_lifts_to_the_floor_and_records_the_lift(self) -> None:
        host = Host((19 * 60 + 25, 19 * 60 + 25, 300))
        assert host._apply_grace_floor(None, first_done=at("18:55")) is True
        assert host.config == (19 * 60 + 55, 19 * 60 + 55, 300)
        assert plan_absorb(0) == (0, 30)

    def test_already_above_the_floor(self) -> None:
        host = Host((21 * 60, 21 * 60, 300))
        assert host._apply_grace_floor(None, first_done=at("18:55")) is False

    def test_no_first_task_no_floor(self) -> None:
        with patch.object(_grace_floor, "first_done_at", return_value=None):
            assert Host((1140, 1140, 300))._apply_grace_floor(None) is False

    def test_unreadable_config(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            assert Host(None)._apply_grace_floor(None, first_done=at("18:55")) is False
        assert "config unreadable" in caplog.text

    def test_failed_write(self, caplog: pytest.LogCaptureFixture) -> None:
        host = Host((1140, 1140, 300), ok=False)
        with caplog.at_level(logging.WARNING):
            assert host._apply_grace_floor(None, first_done=at("18:55")) is False
        assert "failed to write" in caplog.text
        assert plan_absorb(0) == (0, 0)

    def test_a_sick_day_has_no_floor(self) -> None:
        """The user's call: the sick-day shutdown wins."""
        _grace_floor_history([_ISO])
        assert sick_on(_DAY)
        host = Host((18 * 60, 18 * 60, 300))
        assert host._apply_grace_floor(None, first_done=at("18:55")) is False
        assert host.config == (18 * 60, 18 * 60, 300)


def _grace_floor_history(days: list[str]) -> None:

    _sick_tracker.SICK_HISTORY_FILE.write_text(json.dumps({"sick_days": days}))
