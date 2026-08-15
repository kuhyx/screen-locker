"""Tests for _weekly_check: is_relaxed_day, count_weekly_workouts,
has_weekly_minimum."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from screen_locker._weekly_check import (
    _RELAXED_WEEKDAYS,
    count_weekly_workouts,
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
    """Tue-Thu are optional; Fri-Mon are enforced lock days."""

    def test_monday_is_enforced(self) -> None:
        """Monday is an enforced day."""
        assert is_relaxed_day(today=_dt(0)) is False

    def test_tuesday_is_relaxed(self) -> None:
        """Tuesday is relaxed."""
        assert is_relaxed_day(today=_dt(1)) is True

    def test_wednesday_is_relaxed(self) -> None:
        """Wednesday is relaxed."""
        assert is_relaxed_day(today=_dt(2)) is True

    def test_thursday_is_relaxed(self) -> None:
        """Thursday is relaxed."""
        assert is_relaxed_day(today=_dt(3)) is True

    def test_friday_is_enforced(self) -> None:
        """Friday is an enforced day."""
        assert is_relaxed_day(today=_dt(4)) is False

    def test_saturday_is_enforced(self) -> None:
        """Saturday is an enforced day."""
        assert is_relaxed_day(today=_dt(5)) is False

    def test_sunday_is_enforced(self) -> None:
        """Sunday is an enforced day."""
        assert is_relaxed_day(today=_dt(6)) is False

    def test_relaxed_weekdays_constant_correct(self) -> None:
        """The relaxed set is exactly Tue/Wed/Thu (weekday 1-3)."""
        assert frozenset({1, 2, 3}) == _RELAXED_WEEKDAYS

    def test_uses_local_time_by_default(self) -> None:
        """Called with no argument it reads local time and still returns a bool."""
        result = is_relaxed_day()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# count_weekly_workouts
# ---------------------------------------------------------------------------


class TestCountWeeklyWorkouts:
    """Counting verified workouts inside the current ISO week."""

    def test_no_log_file_returns_zero(self, tmp_path: Path) -> None:
        """A missing log counts as zero rather than raising."""
        log = tmp_path / "workout_log.json"
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_corrupt_json_returns_zero(self, tmp_path: Path) -> None:
        """Unparsable JSON counts as zero rather than raising."""
        log = tmp_path / "workout_log.json"
        log.write_text("{not valid json}")
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_oserror_returns_zero(self, tmp_path: Path) -> None:
        """An unreadable log counts as zero rather than raising."""
        log = tmp_path / "workout_log.json"
        log.write_text("{}")
        with patch("builtins.open", side_effect=OSError("no permission")):
            assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_counts_phone_verified_in_current_week(self, tmp_path: Path) -> None:
        """Two phone-verified days in the same week count as two."""
        log = tmp_path / "workout_log.json"
        # Mon=2025-05-19, Tue=2025-05-20 both in same week; check on Fri=2025-05-23
        _make_log({"2025-05-19": "phone_verified", "2025-05-20": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 2

    def test_sick_day_not_counted(self, tmp_path: Path) -> None:
        """A sick day is not a workout."""
        log = tmp_path / "workout_log.json"
        _make_log({"2025-05-19": "sick_day"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_early_bird_not_counted(self, tmp_path: Path) -> None:
        """An early-bird entry is not a workout."""
        log = tmp_path / "workout_log.json"
        _make_log({"2025-05-19": "early_bird"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_previous_week_not_counted(self, tmp_path: Path) -> None:
        """Last week's workouts do not count toward this week."""
        log = tmp_path / "workout_log.json"
        # 2025-05-12 is the Monday of the previous week
        _make_log({"2025-05-12": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_future_date_not_counted(self, tmp_path: Path) -> None:
        """A date after today does not count, even in the same week."""
        log = tmp_path / "workout_log.json"
        # 2025-05-24 is Saturday, checking on Friday 2025-05-23
        _make_log({"2025-05-24": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_invalid_date_key_skipped(self, tmp_path: Path) -> None:
        """An unparsable date key is skipped, and valid siblings still count."""
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
        """An entry that is not a dict is skipped rather than raising."""
        log = tmp_path / "workout_log.json"
        data: dict[str, Any] = {"2025-05-19": "not-a-dict"}
        log.write_text(json.dumps(data))
        assert count_weekly_workouts(log, today=_dt(4)) == 0

    def test_counts_up_to_four(self, tmp_path: Path) -> None:
        """Four workouts in one week count as four (no cap below the minimum)."""
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
        """Today's own workout counts."""
        log = tmp_path / "workout_log.json"
        # today is Friday 2025-05-23
        _make_log({"2025-05-23": "phone_verified"}, log)
        assert count_weekly_workouts(log, today=_dt(4)) == 1

    def test_monday_start_of_week_counted(self, tmp_path: Path) -> None:
        """Monday is the first day of the week, so it counts when checked on Monday."""
        log = tmp_path / "workout_log.json"
        _make_log({"2025-05-19": "phone_verified"}, log)
        # Checking on Monday itself (today=Mon)
        assert count_weekly_workouts(log, today=_dt(0)) == 1

    def test_mixed_types_only_verified_counted(self, tmp_path: Path) -> None:
        """Only verified workouts count; sick/early-bird entries are ignored."""
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

    def test_multiple_same_day_manual_workouts_each_count(self, tmp_path: Path) -> None:
        """Manual workouts count individually now, same as verified — no
        once-per-day collapse."""
        log = tmp_path / "workout_log.json"
        log.write_text(
            json.dumps(
                {
                    "2025-05-19": [
                        {"workout_data": {"type": "manual_workout"}},
                        {"workout_data": {"type": "manual_workout"}},
                    ],
                }
            )
        )
        assert count_weekly_workouts(log, today=_dt(4)) == 2


# ---------------------------------------------------------------------------
# has_weekly_minimum
# ---------------------------------------------------------------------------
