"""Push the PC's workouts to the shared Firebase sync store.

``log.json`` is the single source of truth: this module derives the
crdt-sync log directly from it and pushes to this device's log, so the
phone converges on the SAME history the PC has — manual workouts *and*
machine-verified ones (StrongLifts sessions, RunnerUp runs).

Deriving from the log (rather than a side-store written at log-time) means a
workout is published automatically no matter when or how it was recorded,
including entries logged before this module existed. Idempotence comes from two
properties: the record id is the workout's own stable ``workout_id``, and its
HLC is derived deterministically from the entry's own timestamp — so re-pushing
an unchanged log produces a byte-identical record set and no store churn.

This reverses the old "the PC only ever reads, never pushes" invariant (it had
no data of its own to contribute). Firebase is the only transport since
2026-10-09; the old GitHub mirror is a frozen archive. Nothing here fails
silently: every path returns a :class:`PushResult` whose ``reason`` says exactly
what happened, and logs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING

from crdt_sync import (
    FileSyncStateStore,
    Hlc,
    LogCodec,
    Record,
    RemoteSyncError,
    RevisionTracking,
    SyncTarget,
    sync_log,
)

from screen_locker._constants import SYNC_STATE_FILE
from screen_locker._device import device_identity
from screen_locker._log_io import load_workout_log
from screen_locker._log_mixin import _derive_workout_id
from screen_locker._sync_retry import with_sync_retry
from screen_locker._sync_tombstones import tombstone_records
from screen_locker._weekly_check import COUNTED_WORKOUT_TYPES
from screen_locker._workout_sync import _DEVICES_PREFIX, sync_client_or_reason

if TYPE_CHECKING:
    from pathlib import Path

    from crdt_sync import Log

_logger = logging.getLogger(__name__)

_PAYLOAD_FIELD = "payload"


@dataclass(frozen=True)
class PushResult:
    """Outcome of :func:`push_pc_workouts` — never silent.

    ``reason`` always states what happened in plain words, whether or not the
    push succeeded, so a caller (and the log) can tell "nothing to do" apart
    from "it broke".
    """

    pushed: bool
    record_count: int
    reason: str


def _encode_log(log: Log) -> str:
    """Serialize a crdt-sync log to JSON (record id -> record dict)."""
    return json.dumps({rid: record.to_dict() for rid, record in log.items()})


def _decode_log(text: str) -> Log:
    """Parse a crdt-sync log blob back into ``{id: Record}``."""
    raw = json.loads(text)
    return {rid: Record.from_dict(data) for rid, data in raw.items()}


def _entry_wall_ms(entry: dict, date: str) -> int:
    """Return the entry's timestamp in epoch ms, falling back to its date.

    The HLC is derived from this, so it must be stable for a given entry — the
    workout's own recorded time is exactly that. A missing/unparsable timestamp
    falls back to that day's midnight UTC (still stable) and says so in the log,
    rather than silently inventing "now", which would churn the repo on every
    push.
    """
    raw = entry.get("timestamp")
    if isinstance(raw, str):
        try:
            return int(datetime.fromisoformat(raw).timestamp() * 1000)
        except ValueError:
            _logger.warning(
                "Workout entry for %s has an unparsable timestamp (%r) — using "
                "that date's midnight for its sync clock",
                date,
                raw,
            )
    else:
        _logger.warning(
            "Workout entry for %s has no timestamp — using that date's midnight "
            "for its sync clock",
            date,
        )
    midnight = datetime.fromisoformat(date).replace(tzinfo=UTC)
    return int(midnight.timestamp() * 1000)


def records_from_workout_log(log_file: Path) -> dict[str, Record]:
    """Derive the crdt-sync log from ``log.json``.

    Every counted workout becomes one record keyed by its ``workout_id`` — the
    same id the phone mints for its own records, so the two sides dedup to one
    rather than doubling. Entries written before ``workout_id`` existed get
    theirs derived the same way it would have been, so history publishes too.
    The payload is the workout's own data plus the ``kind``/``date`` the wire
    contract requires.
    """
    identity = device_identity()
    log: dict[str, Record] = {}
    for date, entries in load_workout_log(log_file).items():
        for entry in entries:
            workout_data = entry.get("workout_data", {})
            if not isinstance(workout_data, dict):
                continue
            if workout_data.get("type") not in COUNTED_WORKOUT_TYPES:
                continue
            record_id = entry.get("workout_id") or _derive_workout_id(
                date, workout_data
            )
            if not record_id:
                _logger.warning(
                    "Workout on %s (type=%r) has no derivable id — NOT synced",
                    date,
                    workout_data.get("type"),
                )
                continue
            payload = {**workout_data, "kind": workout_data["type"], "date": date}
            hlc = Hlc.new_tick(
                identity.device_id, wall_time_ms=_entry_wall_ms(entry, date)
            )
            log[str(record_id)] = Record(
                id=str(record_id), fields={_PAYLOAD_FIELD: (payload, hlc)}
            )
    # Re-pushed every tick: sync_log never reads this device's own remote
    # log, so a tombstone written once is overwritten by the next push.
    log.update(tombstone_records())
    return log


def push_pc_workouts(log_file: Path) -> PushResult:
    """Publish every counted workout in ``log_file`` to this device's log.

    Runs one full sync tick, so it also retries anything a previous push failed
    to publish. It never raises into the caller — but it is never silent either:
    the returned :class:`PushResult` and a WARNING say why a push did not happen.
    """
    identity = device_identity()
    log = records_from_workout_log(log_file)
    if not log:
        reason = f"no counted workouts in {log_file}"
        _logger.warning("Workouts NOT synced: %s", reason)
        return PushResult(pushed=False, record_count=0, reason=reason)

    client, reason = sync_client_or_reason()
    if client is None:
        # sync_client_or_reason has already said why, in full; this line
        # ties that cause to the records it just stranded.
        _logger.warning(
            "Workouts NOT synced: %d workout(s) stay local — %s", len(log), reason
        )
        return PushResult(pushed=False, record_count=len(log), reason=reason)
    try:
        with_sync_retry(
            lambda: sync_log(
                SyncTarget(
                    client=client,
                    device_id=identity.device_id,
                    legacy_device_id=identity.legacy_id,
                    path_prefix=_DEVICES_PREFIX,
                ),
                log,
                LogCodec(
                    decode=_decode_log,
                    encode=_encode_log,
                ),
                RevisionTracking(
                    state_store=FileSyncStateStore(SYNC_STATE_FILE),
                ),
            ),
            description="push PC workouts",
        )
    except RemoteSyncError as exc:
        # Report what actually happened, nothing more: this used to assert
        # "a 403 means the token lacks contents:write" for every failure,
        # including a plain network error, which sent a 2026-07-20
        # investigation chasing a permissions bug that did not exist.
        reason = f"sync error: {exc}"
        _logger.warning("Workout sync push FAILED for %d workout(s): %s", len(log), exc)
        return PushResult(pushed=False, record_count=len(log), reason=reason)

    _logger.info("Synced %d workout(s) to Firebase", len(log))
    return PushResult(pushed=True, record_count=len(log), reason="pushed")
