"""Wiring of future-dated manual workouts: push, sync pass, poke reset, budget helper."""
# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import Record

from screen_locker import _manual_push, _poke_credit
from screen_locker._log_mixin import write_signed_entry
from screen_locker._manual_pending import add_pending, local_pending_records
from screen_locker._manual_push import push_pc_workouts, records_from_workout_log
from screen_locker._manual_workout import MANUAL_WORKOUT_TYPE
from screen_locker._manual_workout_types import manual_credit_dates
from screen_locker._poke_credit import PokeLocker
from screen_locker._sync_tombstones import add_tombstone
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_RID = "manual:2026-10-17T18:00"
_PAYLOAD = {"kind": "manual_workout", "date": "2026-10-17", "start_time": "18:00"}


def _write_manual(log_file: Path, record_id: str, day: str) -> None:
    """Write one manual workout with a given id into a real signed log."""
    data = {"type": MANUAL_WORKOUT_TYPE, "start_time": "18:00", "workout_id": record_id}
    write_signed_entry(log_file, day, data)


class TestPushPublishesThePendingLedger:
    """A one-shot publish would be erased by the next push; the ledger is re-pushed."""

    def test_a_pending_entry_is_published_even_with_an_empty_log(
        self, tmp_path: Path
    ) -> None:
        add_pending(_RID, dict(_PAYLOAD), "pc-1")
        records = records_from_workout_log(tmp_path / "log.json")
        assert list(records) == [_RID]
        assert records[_RID].fields["payload"][0] == _PAYLOAD

    def test_the_logs_own_copy_wins_once_ingested(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        _write_manual(log_file, _RID, "2026-10-17")
        add_pending(_RID, {**_PAYLOAD, "marker": "ledger"}, "pc-1")
        payload = records_from_workout_log(log_file)[_RID].fields["payload"][0]
        assert "marker" not in payload

    def test_a_tombstone_beats_the_pending_entry(self, tmp_path: Path) -> None:
        add_pending(_RID, dict(_PAYLOAD), "pc-1")
        add_tombstone(_RID, "pc-1", "deleted")
        assert records_from_workout_log(tmp_path / "log.json")[_RID].deleted

    def test_a_push_drops_entries_the_merge_shows_deleted(self, tmp_path: Path) -> None:
        add_pending(_RID, dict(_PAYLOAD), "pc-1")
        merged = {_RID: Record(id=_RID, fields={}, deleted=True)}
        with (
            patch.object(
                _manual_push, "sync_client_or_reason", return_value=(MagicMock(), "")
            ),
            patch.object(_manual_push, "sync_log", return_value=merged),
        ):
            result = push_pc_workouts(tmp_path / "log.json")
        assert result.pushed is True
        assert local_pending_records() == []

    def test_a_push_keeps_a_live_pending_entry(self, tmp_path: Path) -> None:
        add_pending(_RID, dict(_PAYLOAD), "pc-1")
        merged = {_RID: records_from_workout_log(tmp_path / "log.json")[_RID]}
        with (
            patch.object(
                _manual_push, "sync_client_or_reason", return_value=(MagicMock(), "")
            ),
            patch.object(_manual_push, "sync_log", return_value=merged),
        ):
            push_pc_workouts(tmp_path / "log.json")
        assert [rid for rid, _ in local_pending_records()] == [_RID]


class TestSyncPassReadsTheLedger:
    """The 15-minute pass and the login pass both ingest due ledger entries."""

    def test_ledger_entries_join_the_pull_without_duplicating_it(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1")
        add_pending(
            "manual:2026-10-18T09:00", {**_PAYLOAD, "date": "2026-10-18"}, "pc-1"
        )
        pulled = [(_RID, {"from": "firebase"})]
        with (
            patch("screen_locker._sync_mixin.push_pc_workouts"),
            patch(
                "screen_locker._sync_mixin.pull_all_manual_records", return_value=pulled
            ),
            patch(
                "screen_locker._sync_mixin.ingest_manual_records", return_value=[]
            ) as ingest,
        ):
            locker._ingest_synced_manual_workouts()
        records = ingest.call_args.args[1]
        assert [rid for rid, _ in records] == [_RID, "manual:2026-10-18T09:00"]
        assert records[0][1] == {"from": "firebase"}

    def test_due_local_entries_are_ingested_with_the_credit_callback(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"stale": "state"}
        add_pending(_RID, dict(_PAYLOAD), "pc-1")
        with patch(
            "screen_locker._sync_mixin.ingest_manual_records", return_value=[_RID]
        ) as ingest:
            locker._ingest_due_local_manual_workouts()
        assert ingest.call_args.args[1] == [(_RID, _PAYLOAD)]
        assert ingest.call_args.kwargs["on_ingested"] == locker._credit_ingested_workout
        assert locker.workout_data == {}


class TestPokeStartTheDay:
    """The new-day reset pass also ingests due scheduled workouts, after the reset."""

    def test_the_reset_is_followed_by_the_local_ingest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def headless(locker_cls: type[PokeLocker]) -> PokeLocker:
            locker = object.__new__(locker_cls)
            locker.log_file = tmp_path / "log.json"
            locker.workout_data = {}
            return locker

        monkeypatch.setattr(_poke_credit, "_headless_locker", headless)
        monkeypatch.setattr(_poke_credit, "process_week_transition", lambda *_: [])
        monkeypatch.setattr(
            _poke_credit,
            "reset_to_base_if_new_day",
            lambda *_a, **_k: calls.append("reset"),
        )
        monkeypatch.setattr(
            PokeLocker,
            "_ingest_due_local_manual_workouts",
            lambda _self: calls.append("ingest"),
        )
        _poke_credit.fresh_locker().start_the_day()
        assert calls == ["reset", "ingest"]


class TestManualCreditDates:
    """One date per credit; unparsable day keys are left out (and warned about)."""

    def test_unparsable_day_keys_are_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        log_file = tmp_path / "log.json"
        _write_manual(log_file, "manual:2026-10-10T18:00", "2026-10-10")
        raw = json.loads(log_file.read_text())
        raw["garbled"] = raw["2026-10-10"]
        log_file.write_text(json.dumps(raw))
        with caplog.at_level("WARNING"):
            assert manual_credit_dates(log_file) == ["2026-10-10"]
        assert "unparsable date key" in caplog.text
