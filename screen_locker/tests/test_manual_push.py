"""Tests for pushing PC-originated manual workouts to the sync repo."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import GitHubSyncError, Hlc, Record

from screen_locker import _manual_push, _workout_sync
from screen_locker._manual_push import (
    _decode_log,
    _encode_log,
    _load_store,
    _max_hlc,
    _store_path,
    push_pc_manuals,
    record_pc_manual,
)

if TYPE_CHECKING:
    from pathlib import Path

_ENTRY = {
    "type": "manual_workout",
    "source": "table tennis at Solec",
    "sport": "table_tennis",
    "start_time": "18:00",
    "end_time": "19:30",
    "location_name": "Solec",
    "rpe": 6,
}


def _hlc(ms: int) -> Hlc:
    return Hlc(wall_time_ms=ms, counter=0, node_id="pc")


def _record(record_id: str, ms: int) -> Record:
    return Record(id=record_id, fields={"payload": ({"x": 1}, _hlc(ms))})


class TestEncodeDecodeRoundTrip:
    def test_round_trips_a_log(self) -> None:
        log = {"manual:a": _record("manual:a", 100)}
        assert _decode_log(_encode_log(log)) == log


class TestLoadStore:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert _load_store(tmp_path / "nope.json") == {}

    def test_corrupt_file_returns_empty(self, tmp_path: Path) -> None:
        store = tmp_path / "manual_sync_log.json"
        store.write_text("{not json")
        assert _load_store(store) == {}

    def test_valid_file_round_trips(self, tmp_path: Path) -> None:
        store = tmp_path / "manual_sync_log.json"
        log = {"manual:a": _record("manual:a", 100)}
        store.write_text(_encode_log(log))
        assert _load_store(store) == log


class TestMaxHlc:
    def test_empty_returns_none(self) -> None:
        assert _max_hlc({}) is None

    def test_returns_greatest_hlc(self) -> None:
        log = {"a": _record("a", 100), "b": _record("b", 300)}
        assert _max_hlc(log) == _hlc(300)

    def test_skips_records_without_a_payload_field(self) -> None:
        no_payload = Record(id="a", fields={"other": (1, _hlc(1))})
        assert _max_hlc({"a": no_payload}) is None


class TestRecordPcManual:
    def test_writes_a_manual_record(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
        record_id = record_pc_manual(log_file, _ENTRY)
        assert record_id.startswith("manual:")
        assert record_id.endswith("T18:00")
        store = _load_store(_store_path(log_file))
        payload, _clock = store[record_id].fields["payload"]
        assert payload["kind"] == "manual_workout"
        assert "date" in payload

    def test_second_record_has_a_greater_clock(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
        record_pc_manual(log_file, {**_ENTRY, "start_time": "18:00"})
        record_pc_manual(log_file, {**_ENTRY, "start_time": "20:00"})
        store = _load_store(_store_path(log_file))
        clocks = sorted(rec.fields["payload"][1] for rec in store.values())
        assert clocks[0] < clocks[1]


class TestPushPcManuals:
    def test_no_token_is_a_no_op(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
        record_pc_manual(log_file, _ENTRY)
        with patch.object(_manual_push, "read_sync_token", return_value=None):
            push_pc_manuals(log_file)  # no exception, no client

    def test_empty_store_is_a_no_op(self, tmp_path: Path) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        log_file = tmp_path / "workout_log.json"
        with patch.object(_manual_push, "GitHubSyncClient") as client_cls:
            push_pc_manuals(log_file)
        client_cls.assert_not_called()

    def test_pushes_when_token_and_store_present(self, tmp_path: Path) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        log_file = tmp_path / "workout_log.json"
        record_pc_manual(log_file, _ENTRY)
        client = MagicMock()
        client.list_directory.return_value = []
        with patch.object(_manual_push, "GitHubSyncClient", return_value=client):
            push_pc_manuals(log_file)
        client.put_file_text.assert_called_once()

    def test_swallows_a_sync_error(self, tmp_path: Path) -> None:
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        log_file = tmp_path / "workout_log.json"
        record_pc_manual(log_file, _ENTRY)
        client = MagicMock()
        client.list_directory.return_value = []
        client.put_file_text.side_effect = GitHubSyncError("403")
        with patch.object(_manual_push, "GitHubSyncClient", return_value=client):
            push_pc_manuals(log_file)  # swallowed, no raise
