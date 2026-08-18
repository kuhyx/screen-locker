"""Tests for the manual-workout pure-logic module."""
# pylint: disable=protected-access

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING

from screen_locker._constants import (
    MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
    MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
    MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS,
    MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
)
from screen_locker._manual_workout import (
    SPORT_OTHER,
    SPORT_TABLE_TENNIS,
    ManualWorkoutDraft,
    budget_summary,
    count_in_window,
    is_budget_exhausted,
)

if TYPE_CHECKING:
    from pathlib import Path

_TODAY = "2026-07-05"


def _write_logs(log_file: Path, entries: dict[str, str]) -> None:
    """Write a log.json with one entry per {date: type} pair."""
    logs = {
        date: {"timestamp": f"{date}T12:00:00+00:00", "workout_data": {"type": wtype}}
        for date, wtype in entries.items()
    }
    log_file.write_text(json.dumps(logs))


class TestCountInWindow:
    """Tests for count_in_window."""

    def test_counts_only_manual_workout_type(self, tmp_path: Path) -> None:
        """Counts only manual workout type."""
        log_file = tmp_path / "log.json"
        _write_logs(
            log_file,
            {
                "2026-07-04": "manual_workout",
                "2026-07-03": "phone_verified",
                "2026-07-02": "manual_workout",
            },
        )
        assert count_in_window(log_file, 7, today=_TODAY) == 2

    def test_respects_window_cutoff(self, tmp_path: Path) -> None:
        """Respects window cutoff."""
        log_file = tmp_path / "log.json"
        _write_logs(
            log_file,
            {
                "2026-07-04": "manual_workout",  # 1 day ago: in 7d
                "2026-06-28": "manual_workout",  # 7 days ago: NOT in 7d (exclusive)
                "2026-06-20": "manual_workout",  # 15 days ago: in 30d, not 7d
            },
        )
        assert count_in_window(log_file, 7, today=_TODAY) == 1
        assert count_in_window(log_file, 30, today=_TODAY) == 3

    def test_missing_file_returns_zero(self, tmp_path: Path) -> None:
        """Missing file returns zero."""
        log_file = tmp_path / "does_not_exist.json"
        assert count_in_window(log_file, 7, today=_TODAY) == 0

    def test_corrupt_json_returns_zero(self, tmp_path: Path) -> None:
        """Corrupt JSON returns zero."""
        log_file = tmp_path / "log.json"
        log_file.write_text("not json")
        assert count_in_window(log_file, 7, today=_TODAY) == 0

    def test_skips_invalid_date_keys(self, tmp_path: Path) -> None:
        """Skips invalid date keys."""
        log_file = tmp_path / "log.json"
        log_file.write_text(
            json.dumps(
                {
                    "not-a-date": {"workout_data": {"type": "manual_workout"}},
                    "2026-07-04": {"workout_data": {"type": "manual_workout"}},
                }
            )
        )
        assert count_in_window(log_file, 7, today=_TODAY) == 1

    def test_returns_zero_when_today_invalid(self, tmp_path: Path) -> None:
        """Returns zero when today invalid."""
        log_file = tmp_path / "log.json"
        _write_logs(log_file, {"2026-07-04": "manual_workout"})
        assert count_in_window(log_file, 7, today="bogus") == 0

    def test_uses_today_default_when_none(self, tmp_path: Path) -> None:
        """Uses today default when none."""
        log_file = tmp_path / "log.json"
        assert count_in_window(log_file, 7) == 0

    def test_multiple_same_day_entries_each_count(self, tmp_path: Path) -> None:
        """Per-entry counting: same-day manual workouts no longer collapse to
        one slot — each consumes its own, matching the new weekly-count
        parity with verified workouts."""
        log_file = tmp_path / "log.json"
        log_file.write_text(
            json.dumps(
                {
                    "2026-07-04": [
                        {"workout_data": {"type": "manual_workout"}},
                        {"workout_data": {"type": "manual_workout"}},
                    ],
                }
            )
        )
        assert count_in_window(log_file, 7, today=_TODAY) == 2


class TestIsBudgetExhausted:
    """Tests for is_budget_exhausted."""

    def test_false_when_under_budget(self, tmp_path: Path) -> None:
        """False when under budget."""
        log_file = tmp_path / "log.json"
        assert is_budget_exhausted(log_file, today=_TODAY) is False

    def test_true_when_weekly_exhausted(self, tmp_path: Path) -> None:
        """True when weekly exhausted."""
        log_file = tmp_path / "log.json"
        entries = {
            f"2026-07-0{4 - i}": "manual_workout"
            for i in range(MANUAL_WORKOUT_BUDGET_PER_7_DAYS)
        }
        _write_logs(log_file, entries)
        assert is_budget_exhausted(log_file, today=_TODAY) is True

    def test_true_when_monthly_exhausted(self, tmp_path: Path) -> None:
        """True when monthly exhausted."""
        log_file = tmp_path / "log.json"
        # MANUAL_WORKOUT_BUDGET_PER_30_DAYS distinct dates, all strictly after
        # the 30d cutoff (2026-06-05) but at/before the 7d cutoff (2026-06-28),
        # so only the 30d window sees them.
        today_dt = datetime.strptime(_TODAY, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dates = [
            (today_dt - timedelta(days=8 + i)).strftime("%Y-%m-%d")
            for i in range(MANUAL_WORKOUT_BUDGET_PER_30_DAYS)
        ]
        entries = dict.fromkeys(dates, "manual_workout")
        _write_logs(log_file, entries)
        assert count_in_window(log_file, 7, today=_TODAY) == 0
        assert is_budget_exhausted(log_file, today=_TODAY) is True


class TestBudgetSummary:
    """Tests for budget_summary."""

    def test_renders_both_windows(self, tmp_path: Path) -> None:
        """Renders both windows."""
        log_file = tmp_path / "log.json"
        _write_logs(log_file, {"2026-07-04": "manual_workout"})
        summary = budget_summary(log_file, today=_TODAY)
        assert "Manual:" in summary
        assert "1/" in summary


_TT_DEFAULT = ManualWorkoutDraft(
    sport=SPORT_TABLE_TENNIS,
    start_time="12:00",
    end_time="14:00",
    location_name="Osrodek Solec",
    transport_method="bike",
    cost="60 PLN",
    rpe=6,
    went_well="x" * MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    to_improve="y" * MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    overall_feeling="z" * MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    matches_won=1,
    matches_lost=4,
    sets_won=2,
    sets_lost=9,
    racket="pro spin",
    balls="nittaku",
)

_OTHER_DEFAULT = ManualWorkoutDraft(
    sport=SPORT_OTHER,
    start_time="09:00",
    end_time="10:00",
    location_name="Squash club",
    transport_method="car",
    cost="30 PLN",
    rpe=5,
    went_well="x" * MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    to_improve="y" * MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    overall_feeling="z" * MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    activity_type_other="squash",
    activity_details="q" * MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS,
)


def _tt_draft(**overrides: object) -> ManualWorkoutDraft:
    """Build a valid table-tennis draft, with overrides applied."""
    return dataclasses.replace(_TT_DEFAULT, **overrides)


def _other_draft(**overrides: object) -> ManualWorkoutDraft:
    """Build a valid "other sport" draft, with overrides applied."""
    return dataclasses.replace(_OTHER_DEFAULT, **overrides)
