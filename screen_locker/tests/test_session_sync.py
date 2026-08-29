"""Tests for ingesting synced StrongLifts sessions into log.json."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._session_sync import (
    build_session_entry,
    ingest_session_records,
    validate_session,
)
from screen_locker._weekly_check import PC_WORKOUT_TYPE, count_weekly_workouts
from screen_locker._workout_sync import pull_all_session_records

if TYPE_CHECKING:
    from pathlib import Path

_DATE = "2026-08-21"
# The ISO week _DATE falls in, for count_weekly_workouts.
_TODAY = datetime(2026, 8, 21, tzinfo=UTC)


def _session(**overrides: object) -> dict:
    """A session payload shaped like the app's WorkoutSession.toJson()."""
    payload: dict = {
        "workout_type": "B",
        "date": _DATE,
        "start_time": f"{_DATE}T10:39:24.531831",
        "duration_seconds": 6474,
        "succeeded": True,
        "exercises": [{"name": "Dumbbell Row", "succeeded": True}],
    }
    payload.update(overrides)
    return payload


class TestValidateSession:
    """The PC re-derives the verdict rather than trusting the record."""

    def test_accepts_a_long_enough_session(self) -> None:
        ok, detail = validate_session(_session())
        assert ok
        assert "108 min" in detail

    def test_rejects_a_session_with_no_exercises(self) -> None:
        ok, detail = validate_session(_session(exercises=[]))
        assert not ok
        assert "no exercises" in detail

    def test_rejects_a_non_list_exercises_field(self) -> None:
        ok, detail = validate_session(_session(exercises="Dumbbell Row"))
        assert not ok
        assert "no exercises" in detail

    def test_rejects_a_short_session(self) -> None:
        ok, detail = validate_session(_session(duration_seconds=10 * 60))
        assert not ok
        assert "10 min" in detail

    def test_rejects_a_non_numeric_duration(self) -> None:
        ok, detail = validate_session(_session(duration_seconds="lots"))
        assert not ok
        assert "not a number" in detail

    def test_accepts_exactly_the_hidden_accept_threshold(self) -> None:
        """35 min passes; the message still advertises the round 40."""
        ok, _ = validate_session(_session(duration_seconds=35 * 60))
        assert ok

    def test_rejects_just_below_the_accept_threshold(self) -> None:
        ok, detail = validate_session(_session(duration_seconds=34 * 60 + 59))
        assert not ok
        # The real bar (35) must never leak into a user-visible string.
        assert "35" not in detail
        assert "40 min" in detail


class TestBuildSessionEntry:
    """The entry names the PC as the source, never the phone."""

    def test_marks_the_workout_as_pc_verified(self) -> None:
        entry = build_session_entry(_session(), "108 min")
        assert entry["type"] == PC_WORKOUT_TYPE
        assert entry["type"] != "phone_verified"

    def test_describes_the_workout_and_its_outcome(self) -> None:
        entry = build_session_entry(_session(), "108 min")
        assert "workout B" in entry["source"]
        assert "all succeeded" in entry["source"]

    def test_reports_a_partial_workout_as_partial(self) -> None:
        entry = build_session_entry(_session(succeeded=False), "107 min")
        assert "partial" in entry["source"]

    def test_carries_the_duration_and_record_id(self) -> None:
        entry = build_session_entry(_session(), "108 min")
        assert entry["duration_minutes"] == "107.9"
        assert entry["sync_record_id"] == f"{_DATE}T10:39:24.531831"


class TestIngestSessionRecords:
    """Ingestion is idempotent and credits only real workouts."""

    def test_appends_a_verified_session_under_its_own_date(
        self, tmp_path: Path
    ) -> None:
        log = tmp_path / "log.json"
        ingested = ingest_session_records(log, [("r1", _session())])
        assert ingested == ["r1"]
        assert count_weekly_workouts(log, today=_TODAY) == 1

    def test_is_idempotent_across_repeated_syncs(self, tmp_path: Path) -> None:
        """The 15-minute timer re-sees every record; it must not re-credit."""
        log = tmp_path / "log.json"
        records = [("r1", _session())]
        assert ingest_session_records(log, records) == ["r1"]
        assert ingest_session_records(log, records) == []
        assert count_weekly_workouts(log, today=_TODAY) == 1

    def test_skips_a_session_with_no_date(self, tmp_path: Path) -> None:
        payload = _session()
        del payload["date"]
        assert ingest_session_records(tmp_path / "log.json", [("r1", payload)]) == []

    def test_skips_a_session_whose_date_is_not_a_string(self, tmp_path: Path) -> None:
        assert (
            ingest_session_records(tmp_path / "log.json", [("r1", _session(date=7))])
            == []
        )

    def test_skips_a_session_that_fails_validation(self, tmp_path: Path) -> None:
        log = tmp_path / "log.json"
        short = _session(duration_seconds=60)
        assert ingest_session_records(log, [("r1", short)]) == []
        assert count_weekly_workouts(log, today=_TODAY) == 0

    def test_calls_back_for_each_newly_ingested_session(self, tmp_path: Path) -> None:
        seen: list[tuple[dict, list]] = []
        ingest_session_records(
            tmp_path / "log.json",
            [("r1", _session())],
            on_ingested=lambda entry, prior: seen.append((entry, prior)),
        )
        assert len(seen) == 1
        assert seen[0][0]["type"] == PC_WORKOUT_TYPE
        assert seen[0][1] == []

    def test_does_not_call_back_for_a_duplicate(self, tmp_path: Path) -> None:
        log = tmp_path / "log.json"
        records = [("r1", _session())]
        ingest_session_records(log, records)
        seen: list[dict] = []
        ingest_session_records(
            log, records, on_ingested=lambda entry, _prior: seen.append(entry)
        )
        assert seen == []


class TestPullAllSessionRecords:
    """Sessions come from every device log, or from none at all."""

    def test_returns_nothing_without_a_sync_client(self) -> None:
        with patch("screen_locker._workout_sync.sync_client", return_value=None):
            assert pull_all_session_records() == []

    def test_returns_the_merged_records(self) -> None:
        merged = {"r1": (_session(), object())}
        with (
            patch("screen_locker._workout_sync.sync_client", return_value=object()),
            patch(
                "screen_locker._workout_sync._merge_device_records",
                return_value=merged,
            ),
        ):
            assert pull_all_session_records() == [("r1", _session())]
