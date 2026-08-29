"""Tests for gather_status's lock-suppression paths.

Split out of test_status_data_part2.py for the 250-line cap: these are the
cases where something (sick day, wake alarm, scheduled skip, relaxed day,
weekly minimum) means no lock is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._status_data import gather_status
from screen_locker.tests.test_status_data import _files

if TYPE_CHECKING:
    from pathlib import Path

# Fixed reference instant: Friday 2024-01-05, 12:00 UTC == 13:00 Europe/Warsaw.
# Outside the 05:00-09:00 early-bird window and not a Tue/Wed/Thu relaxed day,
# so lock-decision branches are fully deterministic regardless of wall clock.
_FRIDAY_NOON_UTC = datetime(2024, 1, 5, 12, 0, tzinfo=UTC)
# Monday of that same ISO week, for Mon-Wed shutdown-band assertions.
_MONDAY_NOON_UTC = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


class TestGatherStatusLockSuppression:
    """Conditions under which gather_status reports no lock is needed."""

    def test_sick_day_marks_today_and_skips_lock(self, tmp_path: Path) -> None:
        """Sick day marks today and skips lock."""
        files = _files(tmp_path)
        (tmp_path / "sick_history.json").write_text(
            json.dumps({"sick_days": ["2024-01-05"], "debt": 1})
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.today.is_sick_day is True
        assert snap.sick_budget.used_7d == 1
        assert snap.sick_budget.debt == 1
        assert snap.lock_explanation.fired is False
        assert snap.lock_explanation.stage == "sick_day"

    def test_sick_budget_exhausted_flag(self, tmp_path: Path) -> None:
        """Sick budget exhausted flag."""
        files = _files(tmp_path)
        (tmp_path / "sick_history.json").write_text(
            json.dumps({"sick_days": ["2024-01-05"], "debt": 0})
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.sick_budget.exhausted is True

    def test_wake_alarm_skip_stops_lock(self, tmp_path: Path) -> None:
        """Wake alarm skip stops lock."""
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=True
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.lock_explanation.fired is False
        assert snap.lock_explanation.stage == "wake_alarm_skip"

    def test_scheduled_skip_stops_lock(self, tmp_path: Path) -> None:
        """Scheduled skip stops lock."""
        files = _files(tmp_path)
        files["scheduled_skips_file"].write_text(json.dumps(["2024-01-05"]))
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.lock_explanation.stage == "scheduled_skip"

    def test_relaxed_day_stops_lock(self, tmp_path: Path) -> None:
        """Tuesday is a relaxed day — is_relaxed_day derives it from `now`."""
        files = _files(tmp_path)
        tuesday_noon = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=tuesday_noon)

        assert snap.lock_explanation.stage == "relaxed_day"

    def test_weekly_minimum_met_stops_lock(self, tmp_path: Path) -> None:
        # Avoid dating anything "today" (2024-01-05): an unsigned today entry
        # trips already_logged before weekly_minimum_met, and does so only
        # when no HMAC key is configured (env-dependent) -- Jan 4 holds two.
        """Weekly minimum met stops lock."""
        files = _files(tmp_path)
        files["log_file"].write_text(
            json.dumps(
                {
                    "2024-01-01": {"workout_data": {"type": "phone_verified"}},
                    "2024-01-02": {"workout_data": {"type": "phone_verified"}},
                    "2024-01-03": {"workout_data": {"type": "phone_verified"}},
                    "2024-01-04": [
                        {"workout_data": {"type": "phone_verified"}},
                        {"workout_data": {"type": "phone_verified"}},
                    ],
                }
            )
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.week.counted_count == 5
        assert snap.week.remaining == 0
        assert snap.week.extra == 0
        assert snap.lock_explanation.stage == "weekly_minimum_met"

    def test_extra_workouts_beyond_minimum(self, tmp_path: Path) -> None:
        """Extra workouts beyond minimum."""
        files = _files(tmp_path)
        # Jan 1-4 one each, Jan 5 (today, Friday — the last day in-week without
        # going into the future) holds two, for 6 counted total: 1 above the
        # new minimum of 5. Also exercises multiple same-day entries each
        # counting individually.
        files["log_file"].write_text(
            json.dumps(
                {
                    "2024-01-01": {"workout_data": {"type": "phone_verified"}},
                    "2024-01-02": {"workout_data": {"type": "phone_verified"}},
                    "2024-01-03": {"workout_data": {"type": "phone_verified"}},
                    "2024-01-04": {"workout_data": {"type": "phone_verified"}},
                    "2024-01-05": [
                        {"workout_data": {"type": "phone_verified"}},
                        {"workout_data": {"type": "phone_verified"}},
                    ],
                }
            )
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.week.extra == 1
        assert snap.week.remaining == 0
