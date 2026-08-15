"""Tests for the read-only status snapshot layer in _status_data.py."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._status_data import _day_status, gather_status
from screen_locker.tests.test_status_data import _files

if TYPE_CHECKING:
    from pathlib import Path

# Fixed reference instant: Friday 2024-01-05, 12:00 UTC == 13:00 Europe/Warsaw.
# Outside the 05:00-09:00 early-bird window and not a Tue/Wed/Thu relaxed day,
# so lock-decision branches are fully deterministic regardless of wall clock.
_FRIDAY_NOON_UTC = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
# Monday of that same ISO week, for Mon-Wed shutdown-band assertions.
_MONDAY_NOON_UTC = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


class TestGatherStatus:
    """gather_status() end-to-end via tmp_path-backed state files."""

    def test_empty_state_full_lock_by_default(self, tmp_path: Path) -> None:
        """Empty state full lock by default."""
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**_files(tmp_path), now=_FRIDAY_NOON_UTC)

        assert snap.today.date == "2024-01-05"
        assert snap.today.entry_types == ()
        assert snap.today.day_count == 0
        assert snap.today.counted is False
        assert snap.today.is_sick_day is False
        assert snap.week.counted_count == 0
        assert snap.week.remaining == 5
        assert snap.week.extra == 0
        assert snap.shutdown.tonight is None
        assert snap.shutdown.rest_of_week[0].hour == 21
        assert snap.shutdown.rest_of_week[0].speculative is False
        assert snap.sick_budget.used_7d == 0
        assert snap.sick_budget.exhausted is False
        assert snap.streak == 0
        assert snap.early_bird_extended is False
        assert snap.lock_explanation.fired is True
        assert snap.lock_explanation.stage == "full_lock_pending_heat_check"

    def test_populated_week_counts_workouts(self, tmp_path: Path) -> None:
        """Populated week counts workouts."""
        files = _files(tmp_path)
        files["log_file"].write_text(
            json.dumps(
                {
                    "2024-01-01": {
                        "workout_data": {
                            "type": "heat_skip",
                            "temperature_celsius": "34",
                        }
                    },
                    "2024-01-03": {
                        "workout_data": {"type": "runnerup_verified", "source": "run"}
                    },
                    "2024-01-05": {
                        "workout_data": {"type": "phone_verified", "source": "gym"}
                    },
                }
            )
        )
        with (
            patch(
                "screen_locker._status_data.has_workout_skip_today", return_value=False
            ),
            patch(
                "screen_locker._compliance_state.verify_entry_hmac", return_value=True
            ),
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.week.counted_count == 2
        assert snap.today.entry_types == ("phone_verified",)
        assert snap.today.day_count == 1
        assert snap.today.source == "gym"
        assert snap.today.counted is True
        assert snap.lock_explanation.fired is False
        assert snap.lock_explanation.stage == "already_logged"

    def test_shutdown_config_present_reflected_in_tonight(self, tmp_path: Path) -> None:
        """Shutdown config present reflected in tonight."""
        files = _files(tmp_path)
        files["shutdown_config_file"].write_text(
            "MON_WED_HOUR=22\nTHU_SUN_HOUR=23\nMORNING_END_HOUR=5\n"
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.shutdown.tonight == (22, 23, 5)

    def test_bonus_streak_and_extended_early_bird_reflected(
        self, tmp_path: Path
    ) -> None:
        """Bonus streak and extended early bird reflected."""
        files = _files(tmp_path)
        files["extra_benefits_file"].write_text(
            json.dumps(
                {
                    "consecutive_5plus_weeks": 2,
                    "weekly_shutdown_bonus_hours": {"2024-W01": 3},
                    "extended_early_bird_iso_weeks": ["2024-W01"],
                }
            )
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.bonus_hours_this_week == 3
        assert snap.streak == 2
        assert snap.early_bird_extended is True
        assert snap.shutdown.rest_of_week[0].hour == 24  # 21 base + 3 bonus

    def test_next_week_preview_is_speculative_rest_of_week_is_not(
        self, tmp_path: Path
    ) -> None:
        """Next week preview is speculative rest of week is not."""
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert all(d.speculative is False for d in snap.shutdown.rest_of_week)
        assert all(d.speculative is True for d in snap.shutdown.next_week_preview)
        assert len(snap.shutdown.rest_of_week) == 7
        assert len(snap.shutdown.next_week_preview) == 7

    def test_corrupt_log_file_treated_as_empty(self, tmp_path: Path) -> None:
        """Corrupt log file treated as empty."""
        files = _files(tmp_path)
        files["log_file"].write_text("{not valid json")
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.week.counted_count == 0
        assert snap.today.entry_types == ()

    def test_now_defaults_to_current_time_when_omitted(self, tmp_path: Path) -> None:
        """Covers the ``now is None`` branch — just needs to not raise."""
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files)

        assert isinstance(snap.generated_at, str)
        datetime.fromisoformat(snap.generated_at)  # must parse without raising


class TestDayStatus:
    """Direct tests for the _day_status helper on a day's entry list."""

    def test_no_entries_not_sick(self) -> None:
        """No entries not sick."""
        day = _day_status(date(2024, 1, 5), [], set())
        assert day.entry_types == ()
        assert day.counted is False
        assert day.day_count == 0
        assert day.is_sick_day is False

    def test_no_entries_but_sick(self) -> None:
        """No entries but sick."""
        day = _day_status(date(2024, 1, 5), [], {"2024-01-05"})
        assert day.is_sick_day is True

    def test_non_dict_entries_dropped(self) -> None:
        """Corrupt log data (non-dict entries in the list) are skipped."""
        day = _day_status(date(2024, 1, 5), ["corrupt-string-entry"], set())
        assert day.entry_types == ()
        assert day.counted is False
        assert day.day_count == 0
        assert day.source == ""

    def test_multiple_entries_count_verified_individually_manual_once(self) -> None:
        """Two verified + two manual on one day → day_count 3, all types listed."""
        day = _day_status(
            date(2024, 1, 5),
            [
                {"workout_data": {"type": "runnerup_verified", "source": "run"}},
                {"workout_data": {"type": "phone_verified", "source": "gym"}},
                {"workout_data": {"type": "manual_workout", "source": "tt"}},
                {"workout_data": {"type": "manual_workout", "source": "squash"}},
            ],
            set(),
        )
        assert day.entry_types == (
            "runnerup_verified",
            "phone_verified",
            "manual_workout",
            "manual_workout",
        )
        assert day.counted is True
        # 2 verified counted individually + all manual entries count once = 3.
        assert day.day_count == 3
        assert day.source == "run · gym · tt · squash"
