"""Tests for the workout-log write chokepoint (append + workout_id dedup)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from screen_locker._log_io import load_workout_log
from screen_locker._log_mixin import write_signed_entry

if TYPE_CHECKING:
    from pathlib import Path


class TestWriteChokepoint:
    """Tests for _derive_workout_id / write_signed_entry append+dedup."""

    def test_explicit_workout_id_wins(self, tmp_path: Path) -> None:
        """An explicit workout_id in workout_data is used verbatim."""
        log_file = tmp_path / "workout_log.json"
        result = write_signed_entry(
            log_file,
            "2026-07-13",
            {"type": "runnerup_verified", "workout_id": "custom:abc"},
        )
        assert result.appended is True
        assert load_workout_log(log_file)["2026-07-13"][0]["workout_id"] == "custom:abc"

    def test_manual_without_start_time_falls_back_to_type_date(
        self, tmp_path: Path
    ) -> None:
        """A manual entry lacking start_time keys on ``{type}:{date}``."""
        log_file = tmp_path / "workout_log.json"
        write_signed_entry(log_file, "2026-07-13", {"type": "manual_workout"})
        entry = load_workout_log(log_file)["2026-07-13"][0]
        assert entry["workout_id"] == "manual_workout:2026-07-13"

    def test_manual_with_start_time_uses_the_sync_record_id(
        self, tmp_path: Path
    ) -> None:
        """A manual entry reuses the sync record id so local+synced dedup."""
        log_file = tmp_path / "workout_log.json"
        write_signed_entry(
            log_file,
            "2026-07-13",
            {"type": "manual_workout", "start_time": "14:00"},
        )
        entry = load_workout_log(log_file)["2026-07-13"][0]
        assert entry["workout_id"] == "manual:2026-07-13T14:00"

    def test_workout_data_without_type_gets_no_id(self, tmp_path: Path) -> None:
        """No type → no derivable id; the entry still appends."""
        log_file = tmp_path / "workout_log.json"
        assert write_signed_entry(log_file, "2026-07-13", {}).appended is True
        assert "workout_id" not in load_workout_log(log_file)["2026-07-13"][0]

    def test_duplicate_workout_id_is_not_appended(self, tmp_path: Path) -> None:
        """Re-writing the same workout is a no-op — idempotent by workout_id."""
        log_file = tmp_path / "workout_log.json"
        data = {"type": "runnerup_verified", "source": "run"}
        assert write_signed_entry(log_file, "2026-07-13", data).appended is True

        second = write_signed_entry(log_file, "2026-07-13", {**data, "source": "again"})
        assert second.appended is False
        # prior_entries reports the day as it already stood, and nothing is added.
        assert len(second.prior_entries) == 1
        assert len(load_workout_log(log_file)["2026-07-13"]) == 1

    def test_legacy_entry_without_id_is_not_duplicated(self, tmp_path: Path) -> None:
        """A pre-workout_id entry must match its own synced copy, not double.

        Regression: the PC began publishing its history, the phone/timer synced
        a legacy manual workout back, and it appended a SECOND copy because the
        stored id was None. The id is now derived for comparison.
        """
        log_file = tmp_path / "workout_log.json"
        legacy = {
            "timestamp": "2026-07-13T07:25:12+00:00",
            "workout_data": {
                "type": "manual_workout",
                "source": "squash",
                "start_time": "14:00",
            },
        }
        log_file.write_text(json.dumps({"2026-07-13": [legacy]}))

        # The same workout arriving back from sync, now carrying its id.
        result = write_signed_entry(
            log_file,
            "2026-07-13",
            {
                "type": "manual_workout",
                "source": "squash",
                "start_time": "14:00",
                "workout_id": "manual:2026-07-13T14:00",
            },
        )
        assert result.appended is False
        assert len(load_workout_log(log_file)["2026-07-13"]) == 1

    def test_malformed_existing_entry_does_not_block_the_append(
        self, tmp_path: Path
    ) -> None:
        """An existing entry with junk workout_data has no id, so it can't match."""
        log_file = tmp_path / "workout_log.json"
        log_file.write_text(
            json.dumps({"2026-07-13": [{"timestamp": "t", "workout_data": "junk"}]})
        )
        result = write_signed_entry(
            log_file, "2026-07-13", {"type": "runnerup_verified"}
        )
        assert result.appended is True
        assert len(load_workout_log(log_file)["2026-07-13"]) == 2

    def test_distinct_workouts_same_day_both_append(self, tmp_path: Path) -> None:
        """Different workout_ids on one day stack (multiple workouts/day)."""
        log_file = tmp_path / "workout_log.json"
        write_signed_entry(log_file, "2026-07-13", {"type": "manual_workout"})
        result = write_signed_entry(
            log_file, "2026-07-13", {"type": "runnerup_verified"}
        )
        assert result.appended is True
        assert len(result.prior_entries) == 1
        assert len(load_workout_log(log_file)["2026-07-13"]) == 2
