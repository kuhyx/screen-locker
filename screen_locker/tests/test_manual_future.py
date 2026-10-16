"""Tests for the future-dated manual-workout date rule and per-date budget."""

from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import TYPE_CHECKING

import pytest

from screen_locker import _manual_future
from screen_locker._log_mixin import write_signed_entry
from screen_locker._manual_future import (
    BudgetUsage,
    budget_closed_for_all_days,
    budget_error_for_date,
    budget_usage_for_date,
    is_future_date,
    parse_workout_date,
    validate_workout_date,
)
from screen_locker._manual_workout import MANUAL_WORKOUT_TYPE

if TYPE_CHECKING:
    from pathlib import Path

_TODAY = "2026-10-16"


def _plus(days: int, base: str = _TODAY) -> str:
    """Return the ISO date ``days`` after ``base``."""
    return (date.fromisoformat(base) + timedelta(days=days)).isoformat()


def _log(tmp_path: Path, *days: str) -> Path:
    """Write one manual workout per day into a real signed log."""
    log_file = tmp_path / "log.json"
    for day in days:
        data = {
            "type": MANUAL_WORKOUT_TYPE,
            "start_time": "18:00",
            "workout_id": f"manual:{day}T18:00",
        }
        write_signed_entry(log_file, day, data)
    return log_file


class TestParseWorkoutDate:
    """Strict YYYY-MM-DD parsing."""

    def test_parses_an_iso_date(self) -> None:
        assert parse_workout_date(" 2026-10-17 ") == date(2026, 10, 17)

    @pytest.mark.parametrize("bad", ["", "tomorrow", "2026-13-01", "20261017"])
    def test_rejects_and_warns(
        self, bad: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            assert parse_workout_date(bad) is None
        assert "not YYYY-MM-DD" in caplog.text


class TestIsFutureDate:
    """Strictly after the reference day, valid dates only."""

    def test_tomorrow_is_future_and_today_is_not(self) -> None:
        assert is_future_date(_plus(1), today=_TODAY) is True
        assert is_future_date(_TODAY, today=_TODAY) is False
        assert is_future_date(_plus(-1), today=_TODAY) is False

    def test_garbage_is_not_future(self) -> None:
        assert is_future_date("nope", today=_TODAY) is False
        assert is_future_date(_plus(1), today="nope") is False

    def test_defaults_to_the_real_local_day(self) -> None:
        assert is_future_date("2999-01-01") is True


class TestValidateWorkoutDate:
    """The one 0..7 days-ahead rule shared by the form and the CLI."""

    @pytest.mark.parametrize("ahead", [0, 1, 7])
    def test_accepts_today_through_plus_seven(self, ahead: int) -> None:
        assert validate_workout_date(_plus(ahead), today=_TODAY) is None

    def test_rejects_the_past(self) -> None:
        error = validate_workout_date(_plus(-1), today=_TODAY)
        assert error is not None
        assert "past" in error

    def test_rejects_eight_days_ahead(self) -> None:
        error = validate_workout_date(_plus(8), today=_TODAY)
        assert error is not None
        assert "8 days ahead" in error

    def test_rejects_a_garbled_date(self) -> None:
        assert validate_workout_date("soon", today=_TODAY) == (
            "Workout date must be YYYY-MM-DD"
        )

    def test_reports_an_unusable_reference_day(self) -> None:
        error = validate_workout_date(_TODAY, today="garbled")
        assert error is not None
        assert "'garbled'" in error

    def test_defaults_to_the_real_local_day(self) -> None:
        assert validate_workout_date("1999-01-01") is not None


class TestBudgetUsage:
    """The fullest windows that contain the workout date."""

    def test_counts_logged_and_pending_in_the_fullest_window(
        self, tmp_path: Path
    ) -> None:
        log_file = _log(tmp_path, _plus(-2))
        usage = budget_usage_for_date(log_file, _plus(1), [_plus(2)])
        assert usage == BudgetUsage(week=2, month=2)
        assert usage is not None
        assert usage.exhausted is True

    def test_an_empty_log_is_not_exhausted(self, tmp_path: Path) -> None:
        usage = budget_usage_for_date(tmp_path / "none.json", _TODAY)
        assert usage == BudgetUsage(week=0, month=0)
        assert usage is not None
        assert usage.exhausted is False

    def test_the_monthly_cap_alone_exhausts(self) -> None:
        assert BudgetUsage(week=0, month=10).exhausted is True
        assert BudgetUsage(week=1, month=9).exhausted is False

    def test_an_unparsable_pending_date_is_ignored(self, tmp_path: Path) -> None:
        usage = budget_usage_for_date(tmp_path / "none.json", _TODAY, ["garbled"])
        assert usage == BudgetUsage(week=0, month=0)

    def test_a_bad_date_has_no_usage(self, tmp_path: Path) -> None:
        assert budget_usage_for_date(tmp_path / "none.json", "x") is None


class TestBudgetErrorForDate:
    """Admission is decided per workout date, not against today's window."""

    def test_a_full_week_refuses_a_day_inside_it(self, tmp_path: Path) -> None:
        log_file = _log(tmp_path, _plus(-6), _plus(-5))
        error = budget_error_for_date(log_file, _TODAY)
        assert error is not None
        assert "max 2 per 7 days" in error

    def test_the_same_week_still_takes_a_day_outside_it(self, tmp_path: Path) -> None:
        log_file = _log(tmp_path, _plus(-6), _plus(-5))
        assert budget_error_for_date(log_file, _plus(1)) is None

    def test_pending_future_entries_hold_their_slot(self, tmp_path: Path) -> None:
        pending = [_plus(1), _plus(2)]
        error = budget_error_for_date(tmp_path / "none.json", _plus(3), pending)
        assert error is not None
        assert budget_error_for_date(tmp_path / "none.json", _plus(9), pending) is None

    def test_the_monthly_cap_applies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # With the real caps a 7-day window always trips first (ten entries in
        # 30 days force two per week), so isolate the 30-day window.
        monkeypatch.setattr(_manual_future, "_WINDOWS", ((30, 2),))
        days = [_plus(-10), _plus(10)]
        error = budget_error_for_date(tmp_path / "none.json", _TODAY, days)
        assert error is not None
        assert "per 30 days" in error

    def test_a_bad_date_is_refused(self, tmp_path: Path) -> None:
        error = budget_error_for_date(tmp_path / "none.json", "later")
        assert error is not None
        assert "YYYY-MM-DD" in error


class TestBudgetClosedForAllDays:
    """The button hides only when no day today..+7 has room."""

    def test_open_when_empty(self, tmp_path: Path) -> None:
        assert not budget_closed_for_all_days(tmp_path / "n.json", today=_TODAY)

    def test_a_full_today_does_not_close_next_week(self, tmp_path: Path) -> None:
        log_file = _log(tmp_path, _plus(-1), _TODAY)
        assert not budget_closed_for_all_days(log_file, today=_TODAY)

    def test_closed_when_every_day_in_range_is_full(self, tmp_path: Path) -> None:
        # Two pending on each side keep every window in today..+7 at the cap.
        pending = [_plus(-3), _plus(-2), _plus(4), _plus(5)]
        assert budget_closed_for_all_days(tmp_path / "n.json", pending, today=_TODAY)

    def test_a_garbled_today_counts_as_closed(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            assert budget_closed_for_all_days(tmp_path / "n.json", today="??")
        assert "budget treated as closed" in caplog.text

    def test_defaults_to_the_real_local_day(self, tmp_path: Path) -> None:
        assert not budget_closed_for_all_days(tmp_path / "n.json")
