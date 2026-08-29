"""Tests for pushing the PC's workouts (from log.json) to the sync repo."""
# pylint: disable=protected-access

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._manual_push import (
    _decode_log,
    _encode_log,
    _entry_wall_ms,
    records_from_workout_log,
)

if TYPE_CHECKING:
    from pathlib import Path


_MANUAL = {
    "type": "manual_workout",
    "source": "table tennis at Solec",
    "start_time": "18:00",
    "rpe": 6,
}
_RUN = {
    "type": "runnerup_verified",
    "source": "Running: 9.8 km in 55 min",
    "distance_km": 9.8,
}


def _write_log(log_file: Path, data: dict) -> None:
    log_file.write_text(json.dumps(data))


def _entry(workout_data: dict, ts: str, workout_id: str | None = None) -> dict:
    entry: dict = {"timestamp": ts, "workout_data": workout_data}
    if workout_id is not None:
        entry["workout_id"] = workout_id
    return entry


class TestEncodeDecodeLog:
    """The crdt log blob round-trips."""

    def test_round_trips(self, tmp_path: Path) -> None:
        """Round trips."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_RUN, "2026-07-13T10:00:00+00:00")]}
        )
        log = records_from_workout_log(log_file)
        assert _decode_log(_encode_log(log)).keys() == log.keys()


class TestEntryWallMs:
    """The HLC clock is derived from the entry's own timestamp — stably."""

    def test_uses_the_entry_timestamp(self) -> None:
        """Uses the entry timestamp."""
        expected = int(datetime(2026, 7, 13, 12, tzinfo=UTC).timestamp() * 1000)
        ms = _entry_wall_ms({"timestamp": "2026-07-13T12:00:00+00:00"}, "2026-07-13")
        assert ms == expected

    def test_unparsable_timestamp_falls_back_to_midnight(self) -> None:
        """Unparsable timestamp falls back to midnight."""
        ms = _entry_wall_ms({"timestamp": "not-a-time"}, "2026-07-13")
        assert ms == _entry_wall_ms({"timestamp": "2026-07-13T00:00:00+00:00"}, "x")

    def test_missing_timestamp_falls_back_to_midnight(self) -> None:
        """Missing timestamp falls back to midnight."""
        expected = int(datetime(2026, 7, 13, tzinfo=UTC).timestamp() * 1000)
        assert _entry_wall_ms({}, "2026-07-13") == expected

    def test_fallback_is_stable_across_calls(self) -> None:
        """The fallback must not be 'now' — that would churn the repo."""
        assert _entry_wall_ms({}, "2026-07-13") == _entry_wall_ms({}, "2026-07-13")


class TestRecordsFromWorkoutLog:
    """log.json is the single source of truth for what gets pushed."""

    def test_derives_a_record_per_counted_workout(self, tmp_path: Path) -> None:
        """Derives a record per counted workout."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file,
            {
                "2026-07-13": [
                    _entry(_MANUAL, "2026-07-13T07:25:12+00:00"),
                    _entry(
                        _RUN,
                        "2026-07-13T23:10:00+00:00",
                        workout_id="runnerup_verified:2026-07-13",
                    ),
                ]
            },
        )
        log = records_from_workout_log(log_file)
        assert set(log) == {"manual:2026-07-13T18:00", "runnerup_verified:2026-07-13"}

    def test_payload_carries_kind_and_date(self, tmp_path: Path) -> None:
        """Payload carries kind and date."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_RUN, "2026-07-13T10:00:00+00:00")]}
        )
        payload, _hlc = records_from_workout_log(log_file)[
            "runnerup_verified:2026-07-13"
        ].fields["payload"]
        assert payload["kind"] == "runnerup_verified"
        assert payload["date"] == "2026-07-13"
        assert payload["distance_km"] == 9.8

    def test_legacy_entry_without_workout_id_still_publishes(
        self, tmp_path: Path
    ) -> None:
        """Entries predating workout_id get the id they would have had."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_MANUAL, "2026-07-13T07:25+00:00")]}
        )
        assert "manual:2026-07-13T18:00" in records_from_workout_log(log_file)

    def test_uncounted_types_are_not_pushed(self, tmp_path: Path) -> None:
        """Uncounted types are not pushed."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file,
            {"2026-07-13": [_entry({"type": "sick_day"}, "2026-07-13T07:00:00+00:00")]},
        )
        assert records_from_workout_log(log_file) == {}

    def test_non_dict_workout_data_is_skipped(self, tmp_path: Path) -> None:
        """Non dict workout data is skipped."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file,
            {
                "2026-07-13": [
                    {"timestamp": "2026-07-13T07:00:00+00:00", "workout_data": "x"}
                ]
            },
        )
        assert records_from_workout_log(log_file) == {}

    def test_entry_without_derivable_id_is_skipped(self, tmp_path: Path) -> None:
        """A counted type with no id can't be deduped, so it isn't synced."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_MANUAL, "2026-07-13T07:00:00+00:00")]}
        )
        with patch("screen_locker._manual_push._derive_workout_id", return_value=None):
            assert records_from_workout_log(log_file) == {}

    def test_is_deterministic_across_calls(self, tmp_path: Path) -> None:
        """Same log → identical records+HLCs, so a re-push is a no-op."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_RUN, "2026-07-13T10:00:00+00:00")]}
        )
        assert _encode_log(records_from_workout_log(log_file)) == _encode_log(
            records_from_workout_log(log_file)
        )
