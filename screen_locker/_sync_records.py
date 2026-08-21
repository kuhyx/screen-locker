"""Decoding sync-log blobs into records, and telling record kinds apart.

Split out of :mod:`screen_locker._workout_sync` to keep every file under the
250-line cap. Re-exported from there, so callers are unchanged.

Everything here is pure: it parses JSON that a caller already fetched. Talking
to GitHub or Firebase stays in ``_workout_sync``.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record

from screen_locker._manual_workout import MANUAL_WORKOUT_SYNC_KIND

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_PAYLOAD_FIELD = "payload"


def _is_manual_payload(payload: object) -> bool:
    """True if a decoded sync payload is a manual-workout record."""
    return isinstance(payload, dict) and payload.get("kind") == MANUAL_WORKOUT_SYNC_KIND


def _is_session_payload(payload: object) -> bool:
    """True if a decoded sync payload is a completed StrongLifts session.

    Identified by SHAPE -- the presence of ``exercises`` -- not by a ``kind``
    field, because the phone app's ``WorkoutSession.toJson()`` emits no ``kind``
    at all. Keying session detection on ``kind`` is what made real sessions
    invisible to the only reader that walks every device directory.

    Shape-matching also excludes the PC-origin ``runnerup_verified`` /
    ``phone_verified`` records that share these device logs: they are non-manual
    too, so "not manual" alone would hand a caller expecting ``exercises`` and
    ``duration_seconds`` a record that has neither.
    """
    return isinstance(payload, dict) and isinstance(payload.get("exercises"), list)


def _session_records(log_json: str) -> dict[str, tuple[dict, Hlc]]:
    """Return ``{record_id: (payload, hlc)}`` for session records in a log blob.

    Raises the same decode errors as :func:`_manual_records`; callers treat a
    corrupt device log as "no sessions from that device".
    """
    return _records_matching(log_json, _is_session_payload)


def _tombstoned_ids(log_json: str) -> set[str]:
    """Return the ids this device log marks deleted.

    Collected separately from :func:`_records_matching` because suppression has
    to be applied across the whole device union, not per file: one device
    tombstoning a record while another still holds it live must delete it, and
    a per-file skip would just let the live copy win the merge.

    Raises the same decode errors as :func:`_records_matching`.
    """
    raw = json.loads(log_json)
    if not isinstance(raw, dict):
        msg = f"top-level sync payload is not a JSON object: {raw!r}"
        raise TypeError(msg)
    return {
        record.id
        for record in (Record.from_dict(data) for data in raw.values())
        if record.deleted
    }


def _records_matching(
    log_json: str, predicate: Callable[[object], bool]
) -> dict[str, tuple[dict, Hlc]]:
    """Return ``{record_id: (payload, hlc)}`` for payloads passing ``predicate``.

    Tombstoned records are skipped. crdt-sync deletion is monotonic -- a
    tombstone can never be resurrected by merging an older, non-deleted copy --
    so ``deleted`` is the only way a workout removed on one device can stop
    counting on another. Without this check, deleting a workout in the phone
    app looked like it worked and then the next 15-minute sync re-ingested it.

    Raises:
        TypeError: If the top-level JSON isn't an object or a record's shape
            doesn't match what :meth:`Record.from_dict` expects.
        KeyError: If a record is missing an expected key.
        ValueError: Via ``json.loads`` or :meth:`crdt_sync.Hlc.from_str`.
    """
    raw = json.loads(log_json)
    if not isinstance(raw, dict):
        msg = f"top-level sync payload is not a JSON object: {raw!r}"
        raise TypeError(msg)
    result: dict[str, tuple[dict, Hlc]] = {}
    for data in raw.values():
        record = Record.from_dict(data)
        if record.deleted:
            _logger.info(
                "Sync record %s is tombstoned — skipping it, so a workout "
                "deleted on another device stops counting here too",
                record.id,
            )
            continue
        field = record.fields.get(_PAYLOAD_FIELD)
        if field is None:
            continue
        payload, hlc = field
        if predicate(payload):
            result[record.id] = (payload, hlc)
    return result


def _manual_records(log_json: str) -> dict[str, tuple[dict, Hlc]]:
    """Return ``{record_id: (payload, hlc)}`` for manual records in a log blob.

    Raises the same decode errors as :func:`_records_matching`; callers treat a
    corrupt device log as "no manual records from that device".
    """
    return _records_matching(log_json, _is_manual_payload)
