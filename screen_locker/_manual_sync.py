"""Ingest phone-/PC-synced manual workouts into ``workout_log.json``.

A manual workout logged on another device (phone form, or the PC form pushed
from elsewhere) arrives via crdt-sync as a ``kind="manual_workout"`` payload
(see :func:`screen_locker._manual_workout.build_sync_payload`). This module
turns those synced payloads into ordinary signed ``manual_workout`` entries in
``workout_log.json`` so they count toward the weekly minimum.

Trust model: the PC never trusts the phone's derived fields. Every synced
manual is re-validated with the same :func:`validate_manual_workout` the local
form uses, re-built with :func:`build_entry`, and only then HMAC-signed by the
PC. A phone can therefore at most add a budget-limited, honour-system
``manual_workout`` — never a ``phone_verified`` one (the session path skips
manual records, see :mod:`screen_locker._workout_sync`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from screen_locker._log_io import load_workout_log
from screen_locker._log_mixin import write_signed_entry
from screen_locker._manual_workout import (
    MANUAL_WORKOUT_SYNC_KIND,
    SPORT_OTHER,
    ManualWorkoutDraft,
    build_entry,
    is_budget_exhausted,
    validate_manual_workout,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

_logger = logging.getLogger(__name__)

# Key under which the source sync record id is stored in the ingested
# ``workout_data`` — makes re-ingestion of the same record idempotent.
_SYNC_ID_FIELD = "sync_record_id"


def _coerce_int(value: object) -> int:
    """Coerce a JSON scalar to int; raise for a non-numeric (skips the record)."""
    if isinstance(value, (int, str)):
        return int(value)
    raise TypeError(value)


def reconstruct_draft(payload: Mapping[str, object]) -> ManualWorkoutDraft | None:
    """Rebuild a :class:`ManualWorkoutDraft` from a synced manual payload.

    Returns None if a required raw field is missing or mistyped, so a malformed
    record is skipped rather than crashing ingestion. Only the raw user inputs
    are read back — the derived fields (``source``, ``duration_minutes``,
    ``type``) are recomputed by :func:`build_entry` on the PC.
    """
    try:
        sport = str(payload["sport"])
        activity_type_other = (
            str(payload.get("activity_type", "")) if sport == SPORT_OTHER else ""
        )
        return ManualWorkoutDraft(
            sport=sport,
            start_time=str(payload["start_time"]),
            end_time=str(payload["end_time"]),
            location_name=str(payload["location_name"]),
            transport_method=str(payload["transport_method"]),
            cost=str(payload["cost"]),
            rpe=_coerce_int(payload["rpe"]),
            went_well=str(payload["went_well"]),
            to_improve=str(payload["to_improve"]),
            overall_feeling=str(payload["overall_feeling"]),
            reservation_phone=str(payload.get("reservation_phone", "")),
            techniques_practiced=str(payload.get("techniques_practiced", "")),
            warm_up_minutes=str(payload.get("warm_up_minutes", "")),
            pain_or_injury=str(payload.get("pain_or_injury", "none")),
            matches_won=_coerce_int(payload.get("matches_won", 0)),
            matches_lost=_coerce_int(payload.get("matches_lost", 0)),
            sets_won=_coerce_int(payload.get("sets_won", 0)),
            sets_lost=_coerce_int(payload.get("sets_lost", 0)),
            racket=str(payload.get("racket", "")),
            balls=str(payload.get("balls", "")),
            activity_type_other=activity_type_other,
            activity_details=str(payload.get("activity_details", "")),
            equipment=str(payload.get("equipment", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        _logger.warning(
            "Synced manual workout payload is malformed (%s: %s) — SKIPPING "
            "this record, so it will not be logged or counted on the PC",
            type(exc).__name__,
            exc,
        )
        return None


def _already_ingested(logs: dict[str, list[dict]], record_id: str) -> bool:
    """True if any logged entry already carries this sync record id.

    Iterates the per-day lists (a day may hold several workouts); a cheap
    early-out before reconstructing the draft. The write chokepoint also dedups
    by ``workout_id``, so this and that are two guards on the same idempotency.
    """
    for entries in logs.values():
        for entry in entries:
            workout_data = entry.get("workout_data", {})
            if (
                isinstance(workout_data, dict)
                and workout_data.get(_SYNC_ID_FIELD) == record_id
            ):
                return True
    return False


def ingest_manual_records(
    log_file: Path,
    records: Iterable[tuple[str, Mapping[str, object]]],
    *,
    today: str | None = None,
) -> list[str]:
    """Ingest synced manual workouts into ``workout_log.json``.

    For each ``(record_id, payload)`` tagged ``kind="manual_workout"``:
    reconstruct + re-validate the draft on the PC, enforce the rate budget, then
    HMAC-sign and APPEND it under its own ``date`` (a day may hold several
    workouts). Idempotent: dedup by ``record_id`` here and by ``workout_id`` in
    the write chokepoint, so re-syncing the same record is a no-op. A back-dated
    ingest raises the weekly count but never pushes tonight's shutdown.
    Returns the record ids actually ingested.
    """
    ingested: list[str] = []
    for record_id, payload in records:
        if payload.get("kind") != MANUAL_WORKOUT_SYNC_KIND:
            continue
        date = payload.get("date")
        if not isinstance(date, str):
            _logger.warning("Manual record %s has no date — skipped", record_id)
            continue
        if _already_ingested(load_workout_log(log_file), record_id):
            continue
        draft = reconstruct_draft(payload)
        if draft is None:
            _logger.warning("Manual record %s is malformed — skipped", record_id)
            continue
        error = validate_manual_workout(draft)
        if error is not None:
            _logger.warning("Manual record %s invalid: %s", record_id, error)
            continue
        if is_budget_exhausted(log_file, today=today):
            _logger.info("Manual-workout budget exhausted — %s not ingested", record_id)
            continue
        entry = build_entry(draft)
        entry[_SYNC_ID_FIELD] = record_id
        write_signed_entry(log_file, date, entry)
        ingested.append(record_id)
    return ingested
