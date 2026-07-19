"""Tests for the manual-workout pure-logic module."""
# pylint: disable=protected-access

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING

import pytest

from screen_locker._constants import (
    MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
    MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
    MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS,
    MANUAL_WORKOUT_MIN_DURATION_MINUTES,
    MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
)
from screen_locker._manual_workout import (
    SPORT_OTHER,
    SPORT_TABLE_TENNIS,
    ManualWorkoutDraft,
    budget_summary,
    build_entry,
    build_sync_payload,
    count_in_window,
    is_budget_exhausted,
    manual_sync_record_id,
    validate_manual_workout,
)

if TYPE_CHECKING:
    from pathlib import Path

_TODAY = "2026-07-05"


def _write_logs(log_file: Path, entries: dict[str, str]) -> None:
    """Write a workout_log.json with one entry per {date: type} pair."""
    logs = {
        date: {"timestamp": f"{date}T12:00:00+00:00", "workout_data": {"type": wtype}}
        for date, wtype in entries.items()
    }
    log_file.write_text(json.dumps(logs))


class TestCountInWindow:
    """Tests for count_in_window."""

    def test_counts_only_manual_workout_type(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
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
        log_file = tmp_path / "workout_log.json"
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
        log_file = tmp_path / "does_not_exist.json"
        assert count_in_window(log_file, 7, today=_TODAY) == 0

    def test_corrupt_json_returns_zero(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
        log_file.write_text("not json")
        assert count_in_window(log_file, 7, today=_TODAY) == 0

    def test_skips_invalid_date_keys(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
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
        log_file = tmp_path / "workout_log.json"
        _write_logs(log_file, {"2026-07-04": "manual_workout"})
        assert count_in_window(log_file, 7, today="bogus") == 0

    def test_uses_today_default_when_none(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
        assert count_in_window(log_file, 7) == 0

    def test_multiple_same_day_entries_each_count(self, tmp_path: Path) -> None:
        """Per-entry counting: same-day manual workouts no longer collapse to
        one slot — each consumes its own, matching the new weekly-count
        parity with verified workouts."""
        log_file = tmp_path / "workout_log.json"
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
        log_file = tmp_path / "workout_log.json"
        assert is_budget_exhausted(log_file, today=_TODAY) is False

    def test_true_when_weekly_exhausted(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
        entries = {
            f"2026-07-0{4 - i}": "manual_workout"
            for i in range(MANUAL_WORKOUT_BUDGET_PER_7_DAYS)
        }
        _write_logs(log_file, entries)
        assert is_budget_exhausted(log_file, today=_TODAY) is True

    def test_true_when_monthly_exhausted(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
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
        log_file = tmp_path / "workout_log.json"
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


class TestValidateManualWorkout:
    """Tests for validate_manual_workout."""

    def test_valid_table_tennis_returns_none(self) -> None:
        assert validate_manual_workout(_tt_draft()) is None

    def test_valid_other_returns_none(self) -> None:
        assert validate_manual_workout(_other_draft()) is None

    def test_rejects_unknown_sport(self) -> None:
        assert validate_manual_workout(_tt_draft(sport="badminton")) is not None

    @pytest.mark.parametrize(
        "field",
        ["start_time", "end_time", "location_name", "transport_method", "cost"],
    )
    def test_rejects_blank_required_field(self, field: str) -> None:
        assert validate_manual_workout(_tt_draft(**{field: "  "})) is not None

    def test_rejects_bad_time_format(self) -> None:
        assert validate_manual_workout(_tt_draft(start_time="noon")) is not None

    def test_rejects_end_before_start(self) -> None:
        assert (
            validate_manual_workout(_tt_draft(start_time="14:00", end_time="12:00"))
            is not None
        )

    def test_rejects_too_short_duration(self) -> None:
        draft = _tt_draft(start_time="12:00", end_time="12:05")
        assert MANUAL_WORKOUT_MIN_DURATION_MINUTES > 5
        assert validate_manual_workout(draft) is not None

    @pytest.mark.parametrize("rpe", [0, 11, -1])
    def test_rejects_rpe_out_of_range(self, rpe: int) -> None:
        assert validate_manual_workout(_tt_draft(rpe=rpe)) is not None

    @pytest.mark.parametrize(
        "field", ["matches_won", "matches_lost", "sets_won", "sets_lost"]
    )
    def test_rejects_negative_table_tennis_counts(self, field: str) -> None:
        assert validate_manual_workout(_tt_draft(**{field: -1})) is not None

    def test_rejects_zero_matches_played(self) -> None:
        draft = _tt_draft(matches_won=0, matches_lost=0)
        assert validate_manual_workout(draft) is not None

    def test_rejects_blank_racket(self) -> None:
        assert validate_manual_workout(_tt_draft(racket="  ")) is not None

    def test_rejects_blank_balls(self) -> None:
        assert validate_manual_workout(_tt_draft(balls="")) is not None

    def test_rejects_blank_activity_type_other(self) -> None:
        assert validate_manual_workout(_other_draft(activity_type_other="")) is not None

    def test_rejects_short_activity_details(self) -> None:
        assert (
            validate_manual_workout(_other_draft(activity_details="too short"))
            is not None
        )

    @pytest.mark.parametrize("field", ["went_well", "to_improve", "overall_feeling"])
    def test_rejects_short_reflection_field(self, field: str) -> None:
        assert validate_manual_workout(_tt_draft(**{field: "short"})) is not None


class TestBuildEntry:
    """Tests for build_entry."""

    def test_table_tennis_entry_shape(self) -> None:
        entry = build_entry(_tt_draft())
        assert entry["type"] == "manual_workout"
        assert entry["sport"] == "table_tennis"
        assert entry["activity_type"] == "table tennis"
        assert entry["source"] == "table tennis at Osrodek Solec"
        assert entry["duration_minutes"] == "120.0"
        assert entry["matches_won"] == 1
        assert entry["matches_lost"] == 4
        assert entry["sets_won"] == 2
        assert entry["sets_lost"] == 9
        assert entry["racket"] == "pro spin"
        assert entry["balls"] == "nittaku"
        assert "activity_details" not in entry
        assert "equipment" not in entry

    def test_other_sport_entry_shape(self) -> None:
        entry = build_entry(_other_draft())
        assert entry["type"] == "manual_workout"
        assert entry["sport"] == "other"
        assert entry["activity_type"] == "squash"
        assert entry["source"] == "squash at Squash club"
        assert entry["activity_details"] == "q" * MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS
        assert "matches_won" not in entry
        assert "racket" not in entry

    def test_duration_minutes_empty_when_unparsable(self) -> None:
        entry = build_entry(_tt_draft(start_time="bogus"))
        assert entry["duration_minutes"] == ""

    def test_strips_whitespace_fields(self) -> None:
        entry = build_entry(_tt_draft(location_name="  Solec  ", racket="  spin  "))
        assert entry["location_name"] == "Solec"
        assert entry["racket"] == "spin"

    def test_pain_or_injury_defaults_to_none(self) -> None:
        entry = build_entry(_tt_draft())
        assert entry["pain_or_injury"] == "none"


# The canonical manual-workout sync payload. This literal is the cross-language
# wire contract shared with the Flutter workout_app: an IDENTICAL literal lives
# in the Dart test suite (manual_workout model test). Neither side's own
# round-trip test can catch a key-name/format drift from the other (e.g.
# went_well vs wentWell, duration_minutes formatting) — only this shared literal
# on both sides does. If you change a field here, change it there too.
_WIRE_DATE = "2026-07-13"
_WIRE_DRAFT = ManualWorkoutDraft(
    sport=SPORT_TABLE_TENNIS,
    start_time="18:00",
    end_time="19:30",
    location_name="Solec",
    transport_method="bike",
    cost="40 PLN",
    rpe=6,
    went_well="Served consistently and moved feet well",
    to_improve="Backhand topspin needs more consistency",
    overall_feeling="Felt strong focused and in good rhythm",
    reservation_phone="600100200",
    techniques_practiced="topspin serve",
    warm_up_minutes="10",
    pain_or_injury="none",
    matches_won=3,
    matches_lost=1,
    sets_won=7,
    sets_lost=4,
    racket="Butterfly",
    balls="Nittaku 3-star",
)
_WIRE_PAYLOAD: dict[str, object] = {
    "type": "manual_workout",
    "source": "table tennis at Solec",
    "sport": "table_tennis",
    "activity_type": "table tennis",
    "start_time": "18:00",
    "end_time": "19:30",
    "duration_minutes": "90.0",
    "location_name": "Solec",
    "transport_method": "bike",
    "cost": "40 PLN",
    "reservation_phone": "600100200",
    "rpe": 6,
    "techniques_practiced": "topspin serve",
    "warm_up_minutes": "10",
    "pain_or_injury": "none",
    "went_well": "Served consistently and moved feet well",
    "to_improve": "Backhand topspin needs more consistency",
    "overall_feeling": "Felt strong focused and in good rhythm",
    "matches_won": 3,
    "matches_lost": 1,
    "sets_won": 7,
    "sets_lost": 4,
    "racket": "Butterfly",
    "balls": "Nittaku 3-star",
    "kind": "manual_workout",
    "date": "2026-07-13",
}


class TestSyncWireFormat:
    """Cross-language wire-format contract for the manual-workout sync payload."""

    def test_build_sync_payload_matches_fixture(self) -> None:
        assert build_sync_payload(_WIRE_DRAFT, _WIRE_DATE) == _WIRE_PAYLOAD

    def test_sync_payload_is_json_serializable(self) -> None:
        # The Dart side round-trips the same literal through JSON; guard that our
        # payload contains only JSON-native types (no stray dataclass/objects).
        restored = json.loads(json.dumps(build_sync_payload(_WIRE_DRAFT, _WIRE_DATE)))
        assert restored == _WIRE_PAYLOAD

    def test_record_id_is_stable_and_prefixed(self) -> None:
        assert manual_sync_record_id(_WIRE_DATE, "18:00") == "manual:2026-07-13T18:00"

    def test_kind_discriminator_present_and_typed(self) -> None:
        payload = build_sync_payload(_WIRE_DRAFT, _WIRE_DATE)
        # Absent-kind means a StrongLifts session; a manual must be tagged.
        assert payload["kind"] == "manual_workout"
