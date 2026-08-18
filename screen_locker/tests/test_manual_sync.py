"""Tests for ingesting synced manual workouts into log.json."""
# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker import _manual_sync
from screen_locker._manual_sync import (
    ingest_manual_records,
    reconstruct_draft,
)
from screen_locker._manual_workout import (
    SPORT_OTHER,
    SPORT_TABLE_TENNIS,
    ManualWorkoutDraft,
    build_sync_payload,
    manual_sync_record_id,
)
from screen_locker._weekly_check import count_weekly_workouts

if TYPE_CHECKING:
    from pathlib import Path

_DATE = "2026-07-13"

_TT_DRAFT = ManualWorkoutDraft(
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
    matches_won=3,
    matches_lost=1,
    sets_won=7,
    sets_lost=4,
    racket="Butterfly",
    balls="Nittaku 3-star",
)
_OTHER_DRAFT = ManualWorkoutDraft(
    sport=SPORT_OTHER,
    start_time="09:00",
    end_time="10:00",
    location_name="Squash club",
    transport_method="car",
    cost="30 PLN",
    rpe=5,
    went_well="Moved well and kept long rallies going",
    to_improve="Need to volley earlier off the back wall",
    overall_feeling="Tired but satisfied with the effort",
    activity_type_other="squash",
    activity_details="Full-court squash drills and three practice games total",
    equipment="racket, goggles",
)


def _manual_record(draft: ManualWorkoutDraft, date: str = _DATE) -> tuple[str, dict]:
    """Build a (record_id, payload) pair as it would arrive from sync."""
    payload = build_sync_payload(draft, date)
    return manual_sync_record_id(date, draft.start_time), payload


class TestReconstructDraft:
    """ReconstructDraft."""

    def test_rebuilds_a_table_tennis_draft(self) -> None:
        """Rebuilds a table tennis draft."""
        _, payload = _manual_record(_TT_DRAFT)
        draft = reconstruct_draft(payload)
        assert draft is not None
        assert draft.sport == SPORT_TABLE_TENNIS
        assert draft.racket == "Butterfly"

    def test_rebuilds_an_other_sport_draft(self) -> None:
        """Rebuilds an other sport draft."""
        _, payload = _manual_record(_OTHER_DRAFT)
        draft = reconstruct_draft(payload)
        assert draft is not None
        assert draft.activity_type_other == "squash"

    def test_returns_none_when_a_required_field_is_missing(self) -> None:
        """Returns none when a required field is missing."""
        _, payload = _manual_record(_TT_DRAFT)
        del payload["start_time"]
        assert reconstruct_draft(payload) is None

    def test_returns_none_on_a_mistyped_field(self) -> None:
        """Returns none on a mistyped field."""
        _, payload = _manual_record(_TT_DRAFT)
        payload["rpe"] = None
        assert reconstruct_draft(payload) is None


class TestIngestManualRecords:
    """IngestManualRecords."""

    def test_ingests_a_valid_record(self, tmp_path: Path) -> None:
        """Ingests a valid record."""
        log_file = tmp_path / "log.json"
        record = _manual_record(_TT_DRAFT)
        ingested = ingest_manual_records(log_file, [record], today=_DATE)
        assert ingested == [record[0]]
        stored = json.loads(log_file.read_text())
        # The log is now a list of entries per day.
        workout = stored[_DATE][0]["workout_data"]
        assert workout["type"] == "manual_workout"
        assert workout["sync_record_id"] == record[0]
        assert count_weekly_workouts(log_file, today=_dt(_DATE)) == 1

    def test_is_idempotent(self, tmp_path: Path) -> None:
        """Is idempotent."""
        log_file = tmp_path / "log.json"
        record = _manual_record(_TT_DRAFT)
        ingest_manual_records(log_file, [record], today=_DATE)
        again = ingest_manual_records(log_file, [record], today=_DATE)
        assert again == []

    def test_skips_a_non_manual_payload(self, tmp_path: Path) -> None:
        """Skips a non manual payload."""
        log_file = tmp_path / "log.json"
        assert (
            ingest_manual_records(log_file, [("s", {"succeeded": True})], today=_DATE)
            == []
        )

    def test_skips_a_record_without_a_date(self, tmp_path: Path) -> None:
        """Skips a record without a date."""
        log_file = tmp_path / "log.json"
        _, payload = _manual_record(_TT_DRAFT)
        del payload["date"]
        assert ingest_manual_records(log_file, [("m", payload)], today=_DATE) == []

    def test_appends_alongside_an_existing_counted_day(self, tmp_path: Path) -> None:
        """A day may hold several workouts: a synced manual is appended next to
        an existing verified entry rather than being skipped (the old
        one-per-day skip is gone)."""
        log_file = tmp_path / "log.json"
        log_file.write_text(
            json.dumps(
                {_DATE: {"workout_data": {"type": "phone_verified"}}},
            )
        )
        record = _manual_record(_TT_DRAFT)
        assert ingest_manual_records(log_file, [record], today=_DATE) == [record[0]]
        stored = json.loads(log_file.read_text())
        # The original phone_verified entry is untouched and the manual is added.
        assert len(stored[_DATE]) == 2
        assert stored[_DATE][0]["workout_data"]["type"] == "phone_verified"
        assert stored[_DATE][1]["workout_data"]["type"] == "manual_workout"

    def test_skips_a_malformed_payload(self, tmp_path: Path) -> None:
        """Skips a malformed payload."""
        log_file = tmp_path / "log.json"
        _, payload = _manual_record(_TT_DRAFT)
        payload["rpe"] = None  # reconstruct_draft -> None
        assert ingest_manual_records(log_file, [("m", payload)], today=_DATE) == []

    def test_skips_an_invalid_draft(self, tmp_path: Path) -> None:
        """Skips an invalid draft."""
        log_file = tmp_path / "log.json"
        _, payload = _manual_record(_TT_DRAFT)
        payload["location_name"] = "   "  # fails validate_manual_workout
        assert ingest_manual_records(log_file, [("m", payload)], today=_DATE) == []

    def test_skips_when_budget_exhausted(self, tmp_path: Path) -> None:
        """Skips when budget exhausted."""
        log_file = tmp_path / "log.json"
        record = _manual_record(_TT_DRAFT)
        with patch.object(_manual_sync, "is_budget_exhausted", return_value=True):
            assert ingest_manual_records(log_file, [record], today=_DATE) == []

    def test_writes_unsigned_entry_when_hmac_key_unavailable(
        self, tmp_path: Path
    ) -> None:
        """Writes unsigned entry when HMAC key unavailable."""
        log_file = tmp_path / "log.json"
        record = _manual_record(_TT_DRAFT)
        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None):
            ingest_manual_records(log_file, [record], today=_DATE)
        stored = json.loads(log_file.read_text())
        assert "hmac" not in stored[_DATE][0]


def _dt(date: str) -> object:
    from datetime import datetime, timezone

    return datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
