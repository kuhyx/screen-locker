"""Tests for _weekly_check: is_relaxed_day, count_weekly_workouts,
has_weekly_minimum."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from python_pkg.screen_locker._weekly_check import (
    _RELAXED_WEEKDAYS,
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
    has_weekly_minimum,
    is_relaxed_day,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(weekday: int, hour: int = 10) -> datetime:
    """Return a UTC-aware datetime for the given ISO weekday (0=Mon, 6=Sun)."""
    # 2025-05-19 is a Monday (weekday 0)
    base = datetime(2025, 5, 19, hour, 0, 0, tzinfo=timezone.utc)
    from datetime import timedelta

    return base + timedelta(days=weekday)


def _make_log(entries: dict[str, str], log_file: Path) -> Path:
    """Write a workout_log.json with given date→workout_type mapping."""
    data: dict[str, Any] = {
        date: {
            "timestamp": f"{date}T10:00:00+00:00",
            "workout_data": {"type": wtype},
        }
        for date, wtype in entries.items()
    }
    log_file.write_text(json.dumps(data))
    return log_file


# ---------------------------------------------------------------------------
# is_relaxed_day
# ---------------------------------------------------------------------------


class TestIsRelaxedDay:
    def test_monday_is_enforced(self) -> None:
        assert is_relaxed_day(today=_dt(0)) is False

    def test_tuesday_is_relaxed(self) -> None:
        assert is_relaxed_day(today=_dt(1)) is True

    def test_wednesday_is_relaxed(self) -> None:
        assert is_relaxed_day(today=_dt(2)) is True

    def test_thursday_is_relaxed(self) -> None:
        assert is_relaxed_day(today=_dt(3)) is True

    def test_friday_is_enforced(self) -> None:
        assert is_relaxed_day(today=_dt(4)) is False

    def test_saturday_is_enforced(self) -> None:
        assert is_relaxed_day(today=_dt(5)) is False

    def test_sunday_is_enforced(self) -> None:
        assert is_relaxed_day(today=_dt(6)) is False

    def test_relaxed_weekdays_constant_correct(self) -> None:
        assert frozenset({1, 2, 3}) == _RELAXED_WEEKDAYS

    def test_uses_local_time_by_default(self) -> None:
        result = is_relaxed_day()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# count_weekly_workouts
# ---------------------------------------------------------------------------


class TestCountWeeklyWorkouts:
    def test_no_log_file_returns_zero(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_corrupt_json_returns_zero(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        log.write_text("{not valid json}")
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_oserror_returns_zero(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        log.write_text("{}")
        with patch("builtins.open", side_effect=OSError("no permission")):
            assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_counts_phone_verified_in_current_week(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        # Mon=2025-05-19, Tue=2025-05-20 both in same week; check on Fri=2025-05-23
        _make_log({"2025-05-19": "phone_verified", "2025-05-20": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 2

    def test_sick_day_not_counted(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log({"2025-05-19": "sick_day"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_early_bird_not_counted(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log({"2025-05-19": "early_bird"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_previous_week_not_counted(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        # 2025-05-12 is the Monday of the previous week
        _make_log({"2025-05-12": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_future_date_not_counted(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        # 2025-05-24 is Saturday, checking on Friday 2025-05-23
        _make_log({"2025-05-24": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_invalid_date_key_skipped(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        data: dict[str, Any] = {
            "not-a-date": {
                "timestamp": "x",
                "workout_data": {"type": "phone_verified"},
            },
            "2025-05-19": {
                "timestamp": "x",
                "workout_data": {"type": "phone_verified"},
            },
        }
        log.write_text(json.dumps(data))
        assert count_weekly_workouts(log, today=_dt(4)) == 1

    def test_non_dict_entry_skipped(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        data: dict[str, Any] = {"2025-05-19": "not-a-dict"}
        log.write_text(json.dumps(data))
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_counts_up_to_four(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "phone_verified",
                "2025-05-21": "phone_verified",
                "2025-05-22": "phone_verified",
            },
            log,
        )
        assert count_weekly_workouts(log, today=_dt(4)) == 4

    def test_today_counts_if_this_week(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        # today is Friday 2025-05-23
        _make_log({"2025-05-23": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 1

    def test_monday_start_of_week_counted(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log({"2025-05-19": "phone_verified"}, log)
        # Checking on Monday itself (today=Mon)
        assert count_weekly_workouts(log, today=_dt(0)) == 1

    def test_mixed_types_only_verified_counted(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "sick_day",
                "2025-05-21": "early_bird",
                "2025-05-22": "phone_verified",
            },
            log,
        )
        assert count_weekly_workouts(log, today=_dt(4)) == 2


# ---------------------------------------------------------------------------
# has_weekly_minimum
# ---------------------------------------------------------------------------


class TestHasWeeklyMinimum:
    def test_zero_workouts_is_false(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        assert has_weekly_minimum(log, today=_dt(4)) is False

    def test_three_workouts_is_false(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "phone_verified",
                "2025-05-21": "phone_verified",
            },
            log,
        )
        assert has_weekly_minimum(log, today=_dt(4)) is False

    def test_four_workouts_is_true(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "phone_verified",
                "2025-05-21": "phone_verified",
                "2025-05-22": "phone_verified",
            },
            log,
        )
        assert has_weekly_minimum(log, today=_dt(4)) is True

    def test_five_workouts_is_true(self, tmp_path: Path) -> None:
        log = tmp_path / "workout_log.json"
        _make_log(
            {
                "2025-05-19": "phone_verified",
                "2025-05-20": "phone_verified",
                "2025-05-21": "phone_verified",
                "2025-05-22": "phone_verified",
                "2025-05-23": "phone_verified",
            },
            log,
        )
        assert has_weekly_minimum(log, today=_dt(4)) is True

    def test_weekly_workout_minimum_constant(self) -> None:
        assert WEEKLY_WORKOUT_MINIMUM == 4
