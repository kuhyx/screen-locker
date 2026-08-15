"""Tests for ingesting synced manual workouts into workout_log.json."""
# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker import _manual_sync
from screen_locker._log_mixin import RecordResult
from screen_locker._manual_sync import (
    ingest_manual_records,
)
from screen_locker._manual_workout import (
    SPORT_OTHER,
    SPORT_TABLE_TENNIS,
    ManualWorkoutDraft,
)
from screen_locker.tests.test_manual_sync import _manual_record

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


class TestIngestManualRecordsCallback:
    """Tests for the ``on_ingested`` callback that drives shutdown/debt credit."""

    def test_on_ingested_called_with_entry_and_prior_entries(
        self, tmp_path: Path
    ) -> None:
        """On ingested called with entry and prior entries."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(
            json.dumps({_DATE: [{"workout_data": {"type": "phone_verified"}}]})
        )
        record = _manual_record(_TT_DRAFT)
        calls: list[tuple[dict, list[dict]]] = []
        ingest_manual_records(
            log_file,
            [record],
            today=_DATE,
            on_ingested=lambda entry, prior: calls.append((entry, prior)),
        )
        assert len(calls) == 1
        entry, prior = calls[0]
        assert entry["type"] == "manual_workout"
        assert entry["sync_record_id"] == record[0]
        assert prior == [{"workout_data": {"type": "phone_verified"}}]

    def test_on_ingested_not_called_when_budget_exhausted(self, tmp_path: Path) -> None:
        """On ingested not called when budget exhausted."""
        log_file = tmp_path / "workout_log.json"
        record = _manual_record(_TT_DRAFT)
        calls: list[tuple[dict, list[dict]]] = []
        with patch.object(_manual_sync, "is_budget_exhausted", return_value=True):
            ingest_manual_records(
                log_file,
                [record],
                today=_DATE,
                on_ingested=lambda entry, prior: calls.append((entry, prior)),
            )
        assert calls == []

    def test_write_chokepoint_collision_is_not_credited_or_returned(
        self, tmp_path: Path
    ) -> None:
        """If the write chokepoint's own workout_id dedup no-ops the write
        (``appended=False``), the record must not be reported as ingested or
        handed to ``on_ingested`` — crediting a write that never happened
        would be a real correctness bug, not just a missed optimization."""
        log_file = tmp_path / "workout_log.json"
        record = _manual_record(_TT_DRAFT)
        calls: list[tuple[dict, list[dict]]] = []
        with patch(
            "screen_locker._manual_sync.write_signed_entry",
            return_value=RecordResult(appended=False, prior_entries=[]),
        ):
            ingested = ingest_manual_records(
                log_file,
                [record],
                today=_DATE,
                on_ingested=lambda entry, prior: calls.append((entry, prior)),
            )
        assert ingested == []
        assert calls == []
