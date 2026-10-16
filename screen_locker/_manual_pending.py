"""Durable ledger of future-dated manual workouts logged on THIS PC.

A manual workout logged for a later day must not enter ``log.json`` until that
day (the weekly check, the budget, the status view and the shutdown derivation
all read the log, and would count it early). It has to live somewhere else, and
be visible to the phone for budget and deletion -- so it is published to this
device's sync log.

Publishing once is not enough, for the reason ``_sync_tombstones`` documents:
``_manual_push`` re-derives this device's log from ``log.json`` on every tick
and ``crdt_sync.sync_log`` never reads the device's OWN remote log back, so
anything published only once is overwritten by the next push. This ledger is
what every push re-publishes (``records_from_workout_log`` merges it in), and
ingestion on the workout's date reads the record back through the ordinary
pull -- the PC does ingest its own device log -- or from here if Firebase is
unreachable that day.

``{record_id: {payload, hlc, scheduled_at}}`` in ``MANUAL_PENDING_FILE``. The HLC
is minted once and stored, so re-pushing the same entry does not churn the
store. An entry leaves the ledger once it is in ``log.json`` (its own copy is
then published from there) or once it is tombstoned.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from crdt_sync import Hlc, Record

from screen_locker._constants import MANUAL_PENDING_FILE
from screen_locker._day import today_str
from screen_locker._log_io import load_workout_log
from screen_locker._log_mixin import _entry_workout_id
from screen_locker._manual_future import parse_workout_date
from screen_locker._manual_workout import MANUAL_WORKOUT_SYNC_KIND
from screen_locker._sync_tombstones import tombstone_records

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

__all__ = [
    "add_pending",
    "local_pending_records",
    "pending_future_dates",
    "pending_ledger_records",
    "settle_pending",
]

_logger = logging.getLogger(__name__)

_PAYLOAD_FIELD = "payload"


def _ledger_path(path: Path | None) -> Path:
    """Resolve the ledger path at call time, so a patched module global applies."""
    return MANUAL_PENDING_FILE if path is None else path


def _load(path: Path) -> dict[str, dict[str, Any]]:
    """Read the ledger; a missing file is empty, a corrupt one is loud."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Pending manual-workout ledger %s is unreadable (%s) -- treating it "
            "as EMPTY, so future-dated workouts logged on this PC will not be "
            "re-published or credited from here",
            path,
            exc,
        )
        return {}
    if not isinstance(raw, dict):
        _logger.warning(
            "Pending manual-workout ledger %s is not a JSON object -- ignoring it",
            path,
        )
        return {}
    return {str(rid): entry for rid, entry in raw.items() if isinstance(entry, dict)}


def _save(path: Path, ledger: dict[str, dict[str, Any]]) -> None:
    """Write the ledger as sorted, indented JSON."""
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def add_pending(
    record_id: str,
    payload: dict[str, object],
    device_id: str,
    path: Path | None = None,
) -> bool:
    """Record a future-dated manual workout. Returns False if already held."""
    path = _ledger_path(path)
    ledger = _load(path)
    if record_id in ledger:
        return False
    ledger[record_id] = {
        "payload": payload,
        "hlc": Hlc.new_tick(device_id).to_str(),
        "scheduled_at": datetime.now(tz=UTC).isoformat(),
    }
    _save(path, ledger)
    return True


def local_pending_records(path: Path | None = None) -> list[tuple[str, dict]]:
    """Return ``(record_id, payload)`` for every ledgered entry not tombstoned.

    The shape ``ingest_manual_records`` takes, so this PC's own future entries
    can be ingested on their date even when the Firebase pull is empty or down.
    """
    dead = tombstone_records().keys()
    return [
        (rid, entry["payload"])
        for rid, entry in _load(_ledger_path(path)).items()
        if rid not in dead and isinstance(entry.get("payload"), dict)
    ]


def pending_ledger_records(path: Path | None = None) -> dict[str, Record]:
    """Return the ledger as crdt_sync records, for ``_manual_push`` to publish.

    An entry without a parsable ``hlc`` is skipped with a warning: publishing
    it clockless would churn the store (or lose to a stale copy).
    """
    records: dict[str, Record] = {}
    for record_id, entry in _load(_ledger_path(path)).items():
        payload = entry.get("payload")
        try:
            hlc = Hlc.from_str(str(entry.get("hlc")))
        except (ValueError, TypeError) as exc:
            _logger.warning(
                "Pending manual workout %s has no usable hlc (%r: %s) -- NOT "
                "published, so the phone will not see it",
                record_id,
                entry.get("hlc"),
                exc,
            )
            continue
        if isinstance(payload, dict):
            records[record_id] = Record(
                id=record_id, fields={_PAYLOAD_FIELD: (payload, hlc)}
            )
    return records


def _logged_ids(log_file: Path) -> set[str]:
    """Every workout id already in ``log.json`` (stored, derived or synced)."""
    ids: set[str] = set()
    for day, entries in load_workout_log(log_file).items():
        for entry in entries:
            if (own := _entry_workout_id(day, entry)) is not None:
                ids.add(own)
            data = entry.get("workout_data", {})
            if isinstance(data, dict) and data.get("sync_record_id"):
                ids.add(str(data["sync_record_id"]))
    return ids


def settle_pending(
    log_file: Path,
    deleted_ids: Iterable[str] = (),
    path: Path | None = None,
) -> list[str]:
    """Drop ledger entries that are in ``log.json`` or deleted; return their ids.

    ``deleted_ids`` come from the merged sync log (a tombstone written on the
    phone reaches it) and the local tombstone ledger is consulted too.
    """
    path = _ledger_path(path)
    ledger = _load(path)
    if not ledger:
        return []
    gone = {*deleted_ids, *tombstone_records().keys(), *_logged_ids(log_file)}
    settled = [rid for rid in ledger if rid in gone]
    for rid in settled:
        del ledger[rid]
    if settled:
        _save(path, ledger)
        _logger.info("Pending manual workout(s) settled and dropped: %s", settled)
    return settled


def pending_future_dates(
    log_file: Path,
    records: Iterable[tuple[str, Mapping[str, object]]],
    *,
    today: str | None = None,
) -> dict[str, str]:
    """Return ``{record_id: date}`` of manual records dated AFTER today.

    ``records`` is the merged Firebase manual pull and/or the local ledger
    (the same record id in both counts once). Ids already in ``log.json`` are
    not pending. Records dated today or earlier are not pending either: they
    were ingested or rejected, and a budget-skipped old record must not keep
    occupying a slot for everyone else.
    """
    reference = today or today_str()
    logged = _logged_ids(log_file)
    pending: dict[str, str] = {}
    for record_id, payload in records:
        day = payload.get("date")
        if (
            payload.get("kind") == MANUAL_WORKOUT_SYNC_KIND
            and isinstance(day, str)
            and parse_workout_date(day) is not None
            and day > reference
            and record_id not in logged
        ):
            pending[record_id] = day
    return pending
