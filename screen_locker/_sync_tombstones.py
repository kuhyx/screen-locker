"""Durable tombstones for workout records the PC must keep deleted in sync.

``_manual_push`` re-derives this device's sync log from ``log.json`` on every
tick and pushes it whole, and ``crdt_sync.sync_log`` pulls only the *other*
devices' logs — so a tombstone written once to the PC's device log is
overwritten by the very next push (observed 2026-09-13: ``--apply`` reported
"tombstoned", the dry run five seconds later reported "LIVE"). Deletion is
monotonic only for records that are still *in* the merge.

The fix is to make the tombstone part of what the PC pushes every time. This
module owns that ledger: ``{record_id: {deleted_hlc, reason, tombstoned_at}}``
in ``SYNC_TOMBSTONES_FILE``. The HLC is minted once and stored, so re-pushing
the same tombstone does not churn the store.

The signed ``log.json`` is never touched — a tombstone only stops the record
from syncing; the local entry stays (see ``scripts/annotate_duplicate_credits.py``
for why this repo annotates rather than deletes).
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from crdt_sync import Hlc, Record

from screen_locker._constants import SYNC_TOMBSTONES_FILE

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


def _load(path: Path) -> dict[str, dict[str, Any]]:
    """Read the ledger; a missing file is an empty ledger, a corrupt one is loud."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Sync tombstone ledger %s is unreadable (%s) — pushing NO tombstones "
            "this tick, so a record deleted here may resurface on other devices",
            path,
            exc,
        )
        return {}
    if not isinstance(raw, dict):
        _logger.warning(
            "Sync tombstone ledger %s is not a JSON object — ignoring it", path
        )
        return {}
    return {str(rid): entry for rid, entry in raw.items() if isinstance(entry, dict)}


def _ledger_path(path: Path | None) -> Path:
    """Resolve the ledger path at call time, so a patched module global applies.

    A default argument would bind the real file at import time and the test
    suite's redirect (``tests/_isolated_state.py``) would silently miss it.
    """
    return SYNC_TOMBSTONES_FILE if path is None else path


def add_tombstone(
    record_id: str,
    device_id: str,
    reason: str,
    path: Path | None = None,
) -> bool:
    """Record *record_id* as deleted. Returns False if it already was."""
    path = _ledger_path(path)
    ledger = _load(path)
    if record_id in ledger:
        return False
    ledger[record_id] = {
        "deleted_hlc": Hlc.new_tick(device_id).to_str(),
        "reason": reason,
        "tombstoned_at": datetime.now(tz=UTC).isoformat(),
    }
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    return True


def tombstone_records(path: Path | None = None) -> dict[str, Record]:
    """Return every ledgered tombstone as a crdt_sync :class:`Record`.

    Entries without a parsable ``deleted_hlc`` are skipped with a warning
    rather than pushed clockless: a tombstone with no HLC still deletes, but
    it cannot be ordered against a later un-delete on another device.
    """
    records: dict[str, Record] = {}
    for record_id, entry in _load(_ledger_path(path)).items():
        hlc_str = entry.get("deleted_hlc")
        try:
            hlc = Hlc.from_str(str(hlc_str))
        except (ValueError, TypeError) as exc:
            _logger.warning(
                "Sync tombstone %s has no usable deleted_hlc (%r: %s) — not pushed",
                record_id,
                hlc_str,
                exc,
            )
            continue
        records[record_id] = Record(
            id=record_id, fields={}, deleted=True, deleted_hlc=hlc
        )
    return records
