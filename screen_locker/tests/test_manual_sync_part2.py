"""Tests for ingesting synced manual workouts into workout_log.json."""
# pylint: disable=protected-access

from __future__ import annotations

from screen_locker import _manual_sync
from screen_locker._manual_workout import (
    SPORT_OTHER,
    SPORT_TABLE_TENNIS,
    ManualWorkoutDraft,
)

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


class TestIngestHelpers:
    """The normalization/dedup helpers behind ingest_manual_records."""

    def test_already_ingested_finds_id_in_per_day_lists(self) -> None:
        """_already_ingested takes normalized ``{date: [entry, ...]}`` and
        scans every entry across all days for a matching sync record id."""
        logs = {
            "a": [],
            "b": [
                {"workout_data": {"type": "manual_workout"}},
                {"workout_data": {"sync_record_id": "x"}},
            ],
        }
        assert _manual_sync._already_ingested(logs, "x") is True
        assert _manual_sync._already_ingested(logs, "y") is False

    def test_already_ingested_ignores_non_dict_workout_data(self) -> None:
        """An entry whose workout_data isn't a dict is skipped, not matched."""
        logs = {"b": [{"workout_data": "not-a-dict"}]}
        assert _manual_sync._already_ingested(logs, "x") is False
