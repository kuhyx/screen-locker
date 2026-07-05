"""Tests for the read-only status snapshot layer in _status_data.py."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._status_data import _day_status, format_summary_line, gather_status

if TYPE_CHECKING:
    from pathlib import Path

# Fixed reference instant: Friday 2024-01-05, 12:00 UTC == 13:00 Europe/Warsaw.
# Outside the 05:00-09:00 early-bird window and not a Tue/Wed/Thu relaxed day,
# so lock-decision branches are fully deterministic regardless of wall clock.
_FRIDAY_NOON_UTC = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
# Monday of that same ISO week, for Mon-Wed shutdown-band assertions.
_MONDAY_NOON_UTC = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


def _files(tmp_path: Path) -> dict[str, Path]:
    return {
        "log_file": tmp_path / "workout_log.json",
        "extra_benefits_file": tmp_path / "extra_benefits_state.json",
        "shutdown_base_file": tmp_path / "shutdown_base.json",
        "shutdown_config_file": tmp_path / "shutdown_config.conf",
        "scheduled_skips_file": tmp_path / "scheduled_skips.json",
        "early_bird_pending_file": tmp_path / "early_bird_pending.json",
    }


class TestGatherStatus:
    """gather_status() end-to-end via tmp_path-backed state files."""

    def test_empty_state_full_lock_by_default(self, tmp_path: Path) -> None:
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**_files(tmp_path), now=_FRIDAY_NOON_UTC)

        assert snap.today.date == "2024-01-05"
        assert snap.today.entry_type is None
        assert snap.today.counted is False
        assert snap.today.is_sick_day is False
        assert snap.week.counted_count == 0
        assert snap.week.remaining == 4
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
        assert snap.today.entry_type == "phone_verified"
        assert snap.today.source == "gym"
        assert snap.today.counted is True
        assert snap.lock_explanation.fired is False
        assert snap.lock_explanation.stage == "already_logged"

    def test_sick_day_marks_today_and_skips_lock(self, tmp_path: Path) -> None:
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
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=True
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.lock_explanation.fired is False
        assert snap.lock_explanation.stage == "wake_alarm_skip"

    def test_scheduled_skip_stops_lock(self, tmp_path: Path) -> None:
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
        tuesday_noon = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=tuesday_noon)

        assert snap.lock_explanation.stage == "relaxed_day"

    def test_weekly_minimum_met_stops_lock(self, tmp_path: Path) -> None:
        files = _files(tmp_path)
        files["log_file"].write_text(
            json.dumps(
                {
                    d: {"workout_data": {"type": "phone_verified"}}
                    for d in ("2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04")
                }
            )
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.week.counted_count == 4
        assert snap.week.remaining == 0
        assert snap.week.extra == 0
        assert snap.lock_explanation.stage == "weekly_minimum_met"

    def test_extra_workouts_beyond_minimum(self, tmp_path: Path) -> None:
        files = _files(tmp_path)
        files["log_file"].write_text(
            json.dumps(
                {
                    d: {"workout_data": {"type": "phone_verified"}}
                    for d in (
                        "2024-01-01",
                        "2024-01-02",
                        "2024-01-03",
                        "2024-01-04",
                        "2024-01-05",
                    )
                }
            )
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.week.extra == 1
        assert snap.week.remaining == 0

    def test_shutdown_config_present_reflected_in_tonight(self, tmp_path: Path) -> None:
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
        files = _files(tmp_path)
        files["log_file"].write_text("{not valid json")
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert snap.week.counted_count == 0
        assert snap.today.entry_type is None

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
    """Direct tests for the _day_status helper's branch on non-dict entries."""

    def test_entry_none_not_sick(self) -> None:
        day = _day_status(date(2024, 1, 5), None, set())
        assert day.entry_type is None
        assert day.counted is False
        assert day.is_sick_day is False

    def test_entry_none_but_sick(self) -> None:
        day = _day_status(date(2024, 1, 5), None, {"2024-01-05"})
        assert day.is_sick_day is True

    def test_entry_not_a_dict(self) -> None:
        """Corrupt log data (non-dict entry) falls back to empty workout_data."""
        day = _day_status(date(2024, 1, 5), "corrupt-string-entry", set())
        assert day.entry_type is None
        assert day.counted is False
        assert day.source == ""


class TestFormatSummaryLine:
    """format_summary_line variants."""

    def test_checkmark_when_week_complete(self, tmp_path: Path) -> None:
        files = _files(tmp_path)
        files["log_file"].write_text(
            json.dumps(
                {
                    d: {"workout_data": {"type": "phone_verified"}}
                    for d in ("2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04")
                }
            )
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert format_summary_line(snap).startswith("✓")

    def test_ellipsis_when_week_incomplete(self, tmp_path: Path) -> None:
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert format_summary_line(snap).startswith("…")

    def test_question_mark_when_no_shutdown_config(self, tmp_path: Path) -> None:
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert "?:00 tonight" not in format_summary_line(snap)
        assert "? tonight" in format_summary_line(snap)

    def test_mon_wed_band_used_on_monday(self, tmp_path: Path) -> None:
        files = _files(tmp_path)
        files["shutdown_config_file"].write_text(
            "MON_WED_HOUR=20\nTHU_SUN_HOUR=23\nMORNING_END_HOUR=5\n"
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_MONDAY_NOON_UTC)

        assert "20:00 tonight" in format_summary_line(snap)

    def test_thu_sun_band_used_on_friday(self, tmp_path: Path) -> None:
        files = _files(tmp_path)
        files["shutdown_config_file"].write_text(
            "MON_WED_HOUR=20\nTHU_SUN_HOUR=23\nMORNING_END_HOUR=5\n"
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert "23:00 tonight" in format_summary_line(snap)
