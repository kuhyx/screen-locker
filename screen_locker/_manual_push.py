"""Push the PC's workouts to the shared sync repo.

``workout_log.json`` is the single source of truth: this module derives the
crdt-sync log directly from it and pushes to ``devices/pc/log.json``, so the
phone converges on the SAME history the PC has — manual workouts *and*
machine-verified ones (StrongLifts sessions, RunnerUp runs).

Deriving from the log (rather than a side-store written at log-time) means a
workout is published automatically no matter when or how it was recorded,
including entries logged before this module existed. Idempotence comes from two
properties: the record id is the workout's own stable ``workout_id``, and its
HLC is derived deterministically from the entry's own timestamp — so re-pushing
an unchanged log produces a byte-identical record set and no repo churn.

This reverses the old "the PC only ever reads, never pushes" invariant (it had
no data of its own to contribute). Pushing needs a sync token with
**contents:write** on the repo — a read-only token 403s. Nothing here fails
silently: every path returns a :class:`PushResult` whose ``reason`` says exactly
what happened, and logs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    SYNC_TOKEN_FILE,
)
from screen_locker._log_io import load_workout_log
from screen_locker._log_mixin import _derive_workout_id
from screen_locker._weekly_check import COUNTED_WORKOUT_TYPES
from screen_locker._workout_sync import _DEVICES_PREFIX, read_sync_token

if TYPE_CHECKING:
    from pathlib import Path

    from crdt_sync import Log

_logger = logging.getLogger(__name__)

_PC_DEVICE_ID = "pc"
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
    midnight = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    return int(midnight.timestamp() * 1000)


def records_from_workout_log(log_file: Path) -> dict[str, Record]:
    """Derive the crdt-sync log from ``workout_log.json``.

    Every counted workout becomes one record keyed by its ``workout_id`` — the
    same id the phone mints for its own records, so the two sides dedup to one
    rather than doubling. Entries written before ``workout_id`` existed get
    theirs derived the same way it would have been, so history publishes too.
    The payload is the workout's own data plus the ``kind``/``date`` the wire
    contract requires.
    """
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
            hlc = Hlc.new_tick(_PC_DEVICE_ID, wall_time_ms=_entry_wall_ms(entry, date))
            log[str(record_id)] = Record(
                id=str(record_id), fields={_PAYLOAD_FIELD: (payload, hlc)}
            )
    return log


def push_pc_workouts(log_file: Path) -> PushResult:
    """Publish every counted workout in ``log_file`` to ``devices/pc/log.json``.

    Runs one full sync tick, so it also retries anything a previous push failed
    to publish. It never raises into the caller — but it is never silent either:
    the returned :class:`PushResult` and a WARNING say why a push did not happen.
    """
    token = read_sync_token()
    if token is None:
        reason = f"no sync token at {SYNC_TOKEN_FILE}"
        _logger.warning(
            "Workouts NOT synced: %s — create a fine-grained GitHub PAT with "
            "contents:write on %s/%s and save it there (chmod 600)",
            reason,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
        )
        return PushResult(pushed=False, record_count=0, reason=reason)

    log = records_from_workout_log(log_file)
    if not log:
        reason = f"no counted workouts in {log_file}"
        _logger.warning("Workouts NOT synced: %s", reason)
        return PushResult(pushed=False, record_count=0, reason=reason)

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
        reason = f"sync error: {exc}"
        _logger.warning(
            "Workout sync push FAILED for %d workout(s): %s — a 403 here means "
            "the token lacks contents:write on %s/%s",
            len(log),
            exc,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
        )
        return PushResult(pushed=False, record_count=len(log), reason=reason)

    _logger.info(
        "Synced %d workout(s) to %s/%s", len(log), SYNC_REPO_OWNER, SYNC_REPO_NAME
    )
    return PushResult(pushed=True, record_count=len(log), reason="pushed")
