"""Push PC-originated manual workouts to the shared sync repo.

The PC manual-workout form writes its entry into ``workout_log.json`` (day-keyed,
locally). For the two-way shared budget, the PC must ALSO publish its manual
workouts to the sync repo so the phone can see them. This module keeps a small
crdt-sync log of *PC-originated* manuals (``manual_sync_log.json``, next to
``workout_log.json``) and pushes it to ``devices/pc/log.json``.

This reverses the old "the PC only ever reads, never pushes" invariant (it had
no data of its own to contribute); manual workouts are that data. Pushing needs
a sync token with **contents:write** on the repo — a read-only token 403s, which
is swallowed (best-effort), so the local form still works offline.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from crdt_sync import (
    GitHubSyncClient,
    GitHubSyncError,
    Hlc,
    Record,
    sync_log,
)

from screen_locker._constants import (
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TIMEOUT_SECONDS,
)
from screen_locker._manual_workout import (
    MANUAL_WORKOUT_SYNC_KIND,
    _today_iso,
    manual_sync_record_id,
)
from screen_locker._workout_sync import _DEVICES_PREFIX, read_sync_token

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from crdt_sync import Log

_logger = logging.getLogger(__name__)

_PC_DEVICE_ID = "pc"
_STORE_FILENAME = "manual_sync_log.json"
_PAYLOAD_FIELD = "payload"


def _store_path(log_file: Path) -> Path:
    """Return the PC manual-sync store path next to ``workout_log.json``."""
    return log_file.parent / _STORE_FILENAME


def _encode_log(log: Log) -> str:
    """Serialize a crdt-sync log to JSON (record id -> record dict)."""
    return json.dumps({rid: record.to_dict() for rid, record in log.items()})


def _decode_log(text: str) -> Log:
    """Parse a crdt-sync log blob back into ``{id: Record}``."""
    raw = json.loads(text)
    return {rid: Record.from_dict(data) for rid, data in raw.items()}


def _load_store(store_file: Path) -> dict[str, Record]:
    """Load the local PC manual store, or ``{}`` if missing/corrupt."""
    if not store_file.exists():
        return {}
    try:
        return dict(_decode_log(store_file.read_text()))
    except (OSError, ValueError, KeyError, TypeError):
        _logger.warning("Corrupt PC manual store at %s — ignoring", store_file)
        return {}


def _max_hlc(log: dict[str, Record]) -> Hlc | None:
    """Return the greatest HLC across the store's payload fields, if any."""
    hlcs = [
        record.fields[_PAYLOAD_FIELD][1]
        for record in log.values()
        if _PAYLOAD_FIELD in record.fields
    ]
    return max(hlcs) if hlcs else None


def record_pc_manual(log_file: Path, entry: Mapping[str, object]) -> str:
    """Record a PC-originated manual workout into the local sync store.

    ``entry`` is the :func:`build_entry` dict the form already produced; this
    wraps it in the shared sync payload (adds ``kind`` + ``date``) under a
    stable ``manual:`` id and appends it to the store with a fresh monotonic
    HLC. Fast and local — the network push happens separately
    (:func:`push_pc_manuals`). Returns the record id.
    """
    date = _today_iso()
    store_file = _store_path(log_file)
    log = _load_store(store_file)
    payload = {**entry, "kind": MANUAL_WORKOUT_SYNC_KIND, "date": date}
    record_id = manual_sync_record_id(date, str(entry.get("start_time", "")))
    hlc = Hlc.new_tick(_PC_DEVICE_ID, previous=_max_hlc(log))
    log[record_id] = Record(id=record_id, fields={_PAYLOAD_FIELD: (payload, hlc)})
    store_file.write_text(_encode_log(log))
    return record_id


def push_pc_manuals(log_file: Path) -> None:
    """Push the PC's manual-workout store to ``devices/pc/log.json``.

    Best-effort: no token, an empty store, or any sync error (notably a 403
    from a read-only token that lacks ``contents:write``) is swallowed so the
    local form keeps working. Runs one full sync tick, so it also retries any
    manuals a previous push failed to publish.
    """
    token = read_sync_token()
    if token is None:
        return
    log = _load_store(_store_path(log_file))
    if not log:
        return
    client = GitHubSyncClient(
        SYNC_REPO_OWNER,
        SYNC_REPO_NAME,
        token,
        timeout_seconds=SYNC_TIMEOUT_SECONDS,
    )
    try:
        sync_log(
            client=client,
            device_id=_PC_DEVICE_ID,
            path_prefix=_DEVICES_PREFIX,
            local_log=log,
            encode=_encode_log,
            decode=_decode_log,
        )
    except GitHubSyncError as exc:
        _logger.info("PC manual push skipped (%s)", exc)
