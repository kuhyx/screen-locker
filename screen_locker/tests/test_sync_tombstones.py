"""Tests for the durable sync-tombstone ledger and its place in every push.

Guards the 2026-09-13 finding: a tombstone written once to the PC's device log
was gone by the next tick, because ``sync_log`` never reads this device's own
remote log and ``_manual_push`` re-derives it from ``log.json`` every time.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record

from screen_locker import _sync_tombstones
from screen_locker._manual_push import records_from_workout_log
from screen_locker._sync_tombstones import add_tombstone, tombstone_records

if TYPE_CHECKING:
    from pathlib import Path

_DEVICE = "57582b3b-01c6-45cc-9674-ad2b95bebf29"
_RID = "manual:2026-09-13T14:30"
_MANUAL = {"type": "manual_workout", "source": "football 11v11", "start_time": "14:30"}


class TestAddTombstone:
    """The ledger is written once per id, with a clock minted at that moment."""

    def test_creates_the_ledger_with_hlc_reason_and_time(self, tmp_path: Path) -> None:
        path = tmp_path / "sync_tombstones.json"
        assert add_tombstone(_RID, _DEVICE, "duplicate", path) is True
        entry = json.loads(path.read_text())[_RID]
        assert Hlc.from_str(entry["deleted_hlc"]).node_id == _DEVICE
        assert entry["reason"] == "duplicate"
        assert entry["tombstoned_at"].startswith("20")

    def test_second_add_is_a_no_op_and_keeps_the_original_clock(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "sync_tombstones.json"
        add_tombstone(_RID, _DEVICE, "first", path)
        before = path.read_text()
        assert add_tombstone(_RID, _DEVICE, "second", path) is False
        assert path.read_text() == before

    def test_adds_alongside_existing_ids(self, tmp_path: Path) -> None:
        path = tmp_path / "sync_tombstones.json"
        add_tombstone(_RID, _DEVICE, "a", path)
        add_tombstone("manual:2026-01-01T08:00", _DEVICE, "b", path)
        assert set(json.loads(path.read_text())) == {_RID, "manual:2026-01-01T08:00"}


class TestTombstoneRecords:
    """Ledger → crdt_sync Records, loud about anything it cannot push."""

    def test_missing_ledger_is_empty(self, tmp_path: Path) -> None:
        assert tombstone_records(tmp_path / "absent.json") == {}

    def test_ledgered_id_becomes_a_deleted_record(self, tmp_path: Path) -> None:
        path = tmp_path / "sync_tombstones.json"
        add_tombstone(_RID, _DEVICE, "duplicate", path)
        record = tombstone_records(path)[_RID]
        assert record == Record(
            id=_RID,
            fields={},
            deleted=True,
            deleted_hlc=Hlc.from_str(json.loads(path.read_text())[_RID]["deleted_hlc"]),
        )

    def test_same_clock_on_every_read(self, tmp_path: Path) -> None:
        """Re-pushing must not churn the store: the HLC is stored, not re-minted."""
        path = tmp_path / "sync_tombstones.json"
        add_tombstone(_RID, _DEVICE, "duplicate", path)
        assert tombstone_records(path) == tombstone_records(path)

    def test_corrupt_ledger_pushes_nothing_and_warns(
        self, tmp_path: Path, caplog
    ) -> None:
        path = tmp_path / "sync_tombstones.json"
        path.write_text("{not json")
        assert tombstone_records(path) == {}
        assert "unreadable" in caplog.text

    def test_non_object_ledger_is_ignored_and_warns(
        self, tmp_path: Path, caplog
    ) -> None:
        path = tmp_path / "sync_tombstones.json"
        path.write_text("[]")
        assert tombstone_records(path) == {}
        assert "not a JSON object" in caplog.text

    def test_non_dict_entries_are_dropped(self, tmp_path: Path) -> None:
        path = tmp_path / "sync_tombstones.json"
        path.write_text(json.dumps({_RID: "garbage"}))
        assert tombstone_records(path) == {}

    def test_entry_without_usable_hlc_is_skipped_and_warns(
        self, tmp_path: Path, caplog
    ) -> None:
        path = tmp_path / "sync_tombstones.json"
        path.write_text(json.dumps({_RID: {"reason": "x"}}))
        assert tombstone_records(path) == {}
        assert "no usable deleted_hlc" in caplog.text


class TestPushCarriesTombstones:
    """records_from_workout_log replaces the live copy with the tombstone."""

    def _log(self, tmp_path: Path) -> Path:
        log_file = tmp_path / "log.json"
        log_file.write_text(
            json.dumps(
                {
                    "2026-09-13": [
                        {
                            "timestamp": "2026-09-13T07:40:06+00:00",
                            "workout_data": _MANUAL,
                            "workout_id": _RID,
                        }
                    ]
                }
            )
        )
        return log_file

    def test_live_entry_is_pushed_when_not_ledgered(self, tmp_path: Path) -> None:
        log = records_from_workout_log(self._log(tmp_path))
        assert log[_RID].deleted is False

    def test_ledgered_entry_is_pushed_as_a_tombstone(self, tmp_path: Path) -> None:
        """The isolated SYNC_TOMBSTONES_FILE (conftest) is what the push reads."""
        add_tombstone(_RID, _DEVICE, "duplicate", _sync_tombstones.SYNC_TOMBSTONES_FILE)
        log = records_from_workout_log(self._log(tmp_path))
        assert log[_RID].deleted is True
        assert log[_RID].fields == {}

    def test_tombstone_for_an_id_not_in_the_log_is_still_pushed(
        self, tmp_path: Path
    ) -> None:
        add_tombstone(
            "manual:2026-01-01T08:00",
            _DEVICE,
            "x",
            _sync_tombstones.SYNC_TOMBSTONES_FILE,
        )
        log = records_from_workout_log(self._log(tmp_path))
        assert log["manual:2026-01-01T08:00"].deleted is True
        assert log[_RID].deleted is False
