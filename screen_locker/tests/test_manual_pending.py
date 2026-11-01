"""Tests for the pending ledger of future-dated manual workouts held on this PC."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from crdt_sync import Hlc

from screen_locker import _manual_pending
from screen_locker._log_mixin import write_signed_entry
from screen_locker._manual_pending import (
    add_pending,
    local_pending_records,
    pending_future_dates,
    pending_ledger_records,
    settle_pending,
)
from screen_locker._manual_workout import MANUAL_WORKOUT_TYPE
from screen_locker._sync_tombstones import add_tombstone

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_RID = "manual:2026-10-17T18:00"
_PAYLOAD = {"kind": "manual_workout", "date": "2026-10-17", "start_time": "18:00"}


def _ledger(tmp_path: Path) -> Path:
    """A ledger path inside tmp_path (nothing exists there yet)."""
    return tmp_path / "pending.json"


def _log_with(tmp_path: Path, record_id: str, day: str) -> Path:
    """A real signed log already holding the workout ``record_id`` on ``day``."""
    log_file = tmp_path / "log.json"
    data = {"type": MANUAL_WORKOUT_TYPE, "start_time": "18:00"}
    data["workout_id"] = record_id
    write_signed_entry(log_file, day, data)
    return log_file


class TestLedgerFile:
    """Reading and writing the ledger is loud about damage."""

    def test_missing_ledger_is_empty(self, tmp_path: Path) -> None:
        """A ledger file that does not exist reads as no pending records."""
        assert local_pending_records(_ledger(tmp_path)) == []

    def test_defaults_to_the_isolated_module_path(self) -> None:
        """With no path given the module's own (test-isolated) ledger file is used."""
        assert _manual_pending._ledger_path(None) == _manual_pending.MANUAL_PENDING_FILE

    def test_corrupt_ledger_is_empty_and_warned(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unparsable JSON yields no records and logs an 'unreadable' warning."""
        path = _ledger(tmp_path)
        path.write_text("{not json")
        with caplog.at_level(logging.WARNING):
            assert local_pending_records(path) == []
        assert "unreadable" in caplog.text

    def test_non_object_ledger_is_ignored_and_warned(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A ledger whose top level is not a JSON object is ignored with a warning."""
        path = _ledger(tmp_path)
        path.write_text("[1, 2]")
        with caplog.at_level(logging.WARNING):
            assert local_pending_records(path) == []
        assert "not a JSON object" in caplog.text

    def test_non_dict_entries_are_dropped(self, tmp_path: Path) -> None:
        """Junk entries that are not dicts are skipped while valid ones survive."""
        path = _ledger(tmp_path)
        path.write_text(json.dumps({"a": "junk", _RID: {"payload": _PAYLOAD}}))
        assert local_pending_records(path) == [(_RID, _PAYLOAD)]


class TestAddPending:
    """Entries are stored once with a stable, minted-once HLC."""

    def test_stores_payload_and_hlc(self, tmp_path: Path) -> None:
        """A new entry is stored with its payload and a parseable HLC."""
        path = _ledger(tmp_path)
        assert add_pending(_RID, dict(_PAYLOAD), "pc-1", path) is True
        stored = json.loads(path.read_text())[_RID]
        assert stored["payload"] == _PAYLOAD
        assert Hlc.from_str(stored["hlc"]) is not None

    def test_a_second_add_is_a_no_op_that_keeps_the_hlc(self, tmp_path: Path) -> None:
        """Adding an existing id returns False and leaves the stored entry untouched."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        first = path.read_text()
        assert add_pending(_RID, {"other": 1}, "pc-1", path) is False
        assert path.read_text() == first


class TestLocalPendingRecords:
    """What ingest reads when Firebase is down on the day."""

    def test_returns_id_and_payload(self, tmp_path: Path) -> None:
        """A stored entry comes back as an (id, payload) pair."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        assert local_pending_records(path) == [(_RID, _PAYLOAD)]

    def test_a_tombstoned_entry_is_not_returned(self, tmp_path: Path) -> None:
        """An entry tombstoned on this PC is hidden from ingest."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        add_tombstone(_RID, "pc-1", "deleted")
        assert local_pending_records(path) == []

    def test_an_entry_without_a_payload_is_skipped(self, tmp_path: Path) -> None:
        """An entry that has no payload field is not returned."""
        path = _ledger(tmp_path)
        path.write_text(json.dumps({_RID: {"hlc": "x"}}))
        assert local_pending_records(path) == []


class TestPendingLedgerRecords:
    """What ``_manual_push`` re-publishes every tick."""

    def test_builds_a_record_with_the_stored_hlc(self, tmp_path: Path) -> None:
        """The republished record carries the payload and the originally minted HLC."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        records = pending_ledger_records(path)
        payload, hlc = records[_RID].fields["payload"]
        assert payload == _PAYLOAD
        assert hlc.to_str() == json.loads(path.read_text())[_RID]["hlc"]

    def test_bad_hlc_is_skipped_and_warned(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unparsable HLC drops the record and warns that it was NOT published."""
        path = _ledger(tmp_path)
        path.write_text(json.dumps({_RID: {"payload": _PAYLOAD, "hlc": "garbage"}}))
        with caplog.at_level(logging.WARNING):
            assert not pending_ledger_records(path)
        assert "NOT published" in caplog.text

    def test_non_dict_payload_is_skipped(self, tmp_path: Path) -> None:
        """An entry whose payload is not a dict is not republished."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        raw = json.loads(path.read_text())
        raw[_RID]["payload"] = "nope"
        path.write_text(json.dumps(raw))
        assert not pending_ledger_records(path)


class TestSettlePending:
    """Entries leave the ledger once logged or deleted."""

    def test_empty_ledger_settles_nothing(self, tmp_path: Path) -> None:
        """Settling an empty ledger removes nothing."""
        assert settle_pending(tmp_path / "log.json", path=_ledger(tmp_path)) == []

    def test_an_entry_already_in_the_log_is_dropped(self, tmp_path: Path) -> None:
        """An entry whose workout already sits in the log leaves the ledger."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        log_file = _log_with(tmp_path, _RID, "2026-10-17")
        assert settle_pending(log_file, path=path) == [_RID]
        assert json.loads(path.read_text()) == {}

    def test_a_synced_copy_in_the_log_also_settles_it(self, tmp_path: Path) -> None:
        """A log entry that carries the id as sync_record_id also settles it."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        log_file = tmp_path / "log.json"
        data = {"type": MANUAL_WORKOUT_TYPE, "sync_record_id": _RID}
        write_signed_entry(log_file, "2026-10-17", data)
        assert settle_pending(log_file, path=path) == [_RID]

    def test_a_deleted_id_from_the_merge_is_dropped(self, tmp_path: Path) -> None:
        """An id reported deleted by the merge is removed from the ledger."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        assert settle_pending(tmp_path / "none.json", [_RID], path) == [_RID]

    def test_a_local_tombstone_is_dropped(self, tmp_path: Path) -> None:
        """A locally tombstoned id is removed from the ledger."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        add_tombstone(_RID, "pc-1", "deleted")
        assert settle_pending(tmp_path / "none.json", path=path) == [_RID]

    def test_a_live_future_entry_stays(self, tmp_path: Path) -> None:
        """An entry that is neither logged nor deleted stays pending."""
        path = _ledger(tmp_path)
        add_pending(_RID, dict(_PAYLOAD), "pc-1", path)
        assert settle_pending(tmp_path / "none.json", path=path) == []
        assert _RID in json.loads(path.read_text())


class TestPendingFutureDates:
    """Which records still hold a future slot."""

    def test_only_manual_records_after_today_count(self, tmp_path: Path) -> None:
        """Only well-formed manual workouts dated after today hold a future slot."""
        records = [
            ("future", {**_PAYLOAD, "date": "2026-10-18"}),
            ("today", {**_PAYLOAD, "date": "2026-10-16"}),
            ("past", {**_PAYLOAD, "date": "2026-10-01"}),
            ("session", {"exercises": [], "date": "2026-10-20"}),
            ("garbled", {**_PAYLOAD, "date": "2026-13-45"}),
            ("nodate", {"kind": "manual_workout"}),
        ]
        found = pending_future_dates(
            tmp_path / "none.json", records, today="2026-10-16"
        )
        assert found == {"future": "2026-10-18"}

    def test_an_already_logged_id_is_not_pending(self, tmp_path: Path) -> None:
        """A record whose id is already in the log is not counted as pending."""
        log_file = _log_with(tmp_path, _RID, "2026-10-17")
        found = pending_future_dates(log_file, [(_RID, _PAYLOAD)], today="2026-10-16")
        assert not found

    def test_defaults_to_the_real_local_day(self, tmp_path: Path) -> None:
        """Without an explicit today the real local day is the cut-off."""
        payload = {**_PAYLOAD, "date": "2999-01-01"}
        found = pending_future_dates(tmp_path / "none.json", [("far", payload)])
        assert found == {"far": "2999-01-01"}

    def test_an_entry_with_no_derivable_id_is_ignored(self, tmp_path: Path) -> None:
        """A log entry from which no id can be derived does not hide a pending record."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({"2026-10-10": [{"workout_data": {}}]}))
        found = pending_future_dates(log_file, [(_RID, _PAYLOAD)], today="2026-10-16")
        assert found == {_RID: "2026-10-17"}
