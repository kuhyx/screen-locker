"""Tests for the manual-workout pure-logic module."""
# pylint: disable=protected-access

from __future__ import annotations

import json

import pytest

from screen_locker._constants import (
    MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)
from screen_locker._manual_workout import (
    SPORT_TABLE_TENNIS,
    ManualWorkoutDraft,
    build_entry,
    build_sync_payload,
    manual_sync_record_id,
    validate_manual_workout,
)
from screen_locker.tests.test_manual_workout import _other_draft, _tt_draft

_TODAY = "2026-07-05"


class TestValidateManualWorkout:
    """Tests for validate_manual_workout."""

    def test_valid_table_tennis_returns_none(self) -> None:
        """Valid table tennis returns none."""
        assert validate_manual_workout(_tt_draft()) is None

    def test_valid_other_returns_none(self) -> None:
        """Valid other returns none."""
        assert validate_manual_workout(_other_draft()) is None

    def test_rejects_unknown_sport(self) -> None:
        """Rejects unknown sport."""
        assert validate_manual_workout(_tt_draft(sport="badminton")) is not None

    @pytest.mark.parametrize(
        "field",
        ["start_time", "end_time", "location_name", "transport_method", "cost"],
    )
    def test_rejects_blank_required_field(self, field: str) -> None:
        """Rejects blank required field."""
        assert validate_manual_workout(_tt_draft(**{field: "  "})) is not None

    def test_rejects_bad_time_format(self) -> None:
        """Rejects bad time format."""
        assert validate_manual_workout(_tt_draft(start_time="noon")) is not None

    def test_rejects_end_before_start(self) -> None:
        """Rejects end before start."""
        assert (
            validate_manual_workout(_tt_draft(start_time="14:00", end_time="12:00"))
            is not None
        )

    def test_rejects_too_short_duration(self) -> None:
        """Rejects too short duration."""
        draft = _tt_draft(start_time="12:00", end_time="12:05")
        assert WORKOUT_DURATION_ACCEPT_MINUTES > 5
        assert validate_manual_workout(draft) is not None

    @pytest.mark.parametrize("rpe", [0, 11, -1])
    def test_rejects_rpe_out_of_range(self, rpe: int) -> None:
        """Rejects rpe out of range."""
        assert validate_manual_workout(_tt_draft(rpe=rpe)) is not None

    @pytest.mark.parametrize(
        "field", ["matches_won", "matches_lost", "sets_won", "sets_lost"]
    )
    def test_rejects_negative_table_tennis_counts(self, field: str) -> None:
        """Rejects negative table tennis counts."""
        assert validate_manual_workout(_tt_draft(**{field: -1})) is not None

    def test_rejects_zero_matches_played(self) -> None:
        """Rejects zero matches played."""
        draft = _tt_draft(matches_won=0, matches_lost=0)
        assert validate_manual_workout(draft) is not None

    def test_rejects_blank_racket(self) -> None:
        """Rejects blank racket."""
        assert validate_manual_workout(_tt_draft(racket="  ")) is not None

    def test_rejects_blank_balls(self) -> None:
        """Rejects blank balls."""
        assert validate_manual_workout(_tt_draft(balls="")) is not None

    def test_rejects_blank_activity_type_other(self) -> None:
        """Rejects blank activity type other."""
        assert validate_manual_workout(_other_draft(activity_type_other="")) is not None

    def test_rejects_short_activity_details(self) -> None:
        """Rejects short activity details."""
        assert (
            validate_manual_workout(_other_draft(activity_details="too short"))
            is not None
        )

    @pytest.mark.parametrize("field", ["went_well", "to_improve", "overall_feeling"])
    def test_rejects_short_reflection_field(self, field: str) -> None:
        """Rejects short reflection field."""
        assert validate_manual_workout(_tt_draft(**{field: "short"})) is not None


class TestBuildEntry:
    """Tests for build_entry."""

    def test_table_tennis_entry_shape(self) -> None:
        """Table tennis entry shape."""
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
        """Other sport entry shape."""
        entry = build_entry(_other_draft())
        assert entry["type"] == "manual_workout"
        assert entry["sport"] == "other"
        assert entry["activity_type"] == "squash"
        assert entry["source"] == "squash at Squash club"
        assert entry["activity_details"] == "q" * MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS
        assert "matches_won" not in entry
        assert "racket" not in entry

    def test_duration_minutes_empty_when_unparsable(self) -> None:
        """Duration minutes empty when unparsable."""
        entry = build_entry(_tt_draft(start_time="bogus"))
        assert entry["duration_minutes"] == ""

    def test_strips_whitespace_fields(self) -> None:
        """Strips whitespace fields."""
        entry = build_entry(_tt_draft(location_name="  Solec  ", racket="  spin  "))
        assert entry["location_name"] == "Solec"
        assert entry["racket"] == "spin"

    def test_pain_or_injury_defaults_to_none(self) -> None:
        """Pain or injury defaults to none."""
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
        """Build sync payload matches fixture."""
        assert build_sync_payload(_WIRE_DRAFT, _WIRE_DATE) == _WIRE_PAYLOAD

    def test_sync_payload_is_json_serializable(self) -> None:
        # The Dart side round-trips the same literal through JSON; guard that our
        # payload contains only JSON-native types (no stray dataclass/objects).
        """Sync payload is JSON serializable."""
        restored = json.loads(json.dumps(build_sync_payload(_WIRE_DRAFT, _WIRE_DATE)))
        assert restored == _WIRE_PAYLOAD

    def test_record_id_is_stable_and_prefixed(self) -> None:
        """Record ID is stable and prefixed."""
        assert manual_sync_record_id(_WIRE_DATE, "18:00") == "manual:2026-07-13T18:00"

    def test_kind_discriminator_present_and_typed(self) -> None:
        """Kind discriminator present and typed."""
        payload = build_sync_payload(_WIRE_DRAFT, _WIRE_DATE)
        # Absent-kind means a StrongLifts session; a manual must be tagged.
        assert payload["kind"] == "manual_workout"
