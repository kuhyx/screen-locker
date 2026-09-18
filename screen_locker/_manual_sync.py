"""Ingest phone-/PC-synced manual workouts into ``log.json``.

A manual workout logged on another device (phone form, or the PC form pushed
from elsewhere) arrives via crdt-sync as a ``kind="manual_workout"`` payload
(see :func:`screen_locker._manual_workout.build_sync_payload`). This module
turns those synced payloads into ordinary signed ``manual_workout`` entries in
``log.json`` so they count toward the weekly minimum and — via the
optional ``on_ingested`` callback — earn the same shutdown/debt reward a
live-logged workout would.

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
from screen_locker._log_mixin import _entry_workout_id, write_signed_entry
from screen_locker._manual_sync_draft import (
    _draft_or_report,
    is_empty_stub,
    reconstruct_draft,
)
from screen_locker._manual_workout import (
    MANUAL_WORKOUT_SYNC_KIND,
    build_entry,
    is_budget_exhausted,
    validate_manual_workout,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    OnIngestedCallback = Callable[[dict, "list[dict]"], None]

__all__ = ["ingest_manual_records", "is_empty_stub", "reconstruct_draft"]

_logger = logging.getLogger(__name__)

# Key under which the source sync record id is stored in the ingested
# ``workout_data`` — makes re-ingestion of the same record idempotent.
_SYNC_ID_FIELD = "sync_record_id"


def _already_ingested(logs: dict[str, list[dict]], record_id: str) -> bool:
    """True if any logged entry already IS this sync record.

    Matches either way a record can already be here: an entry ingested from
    sync carries the id in ``sync_record_id``; an entry logged on this PC
    (form or CLI) and then published carries it as its own ``workout_id``,
    since the publisher keys records on exactly that. Checking only the first
    is how the 2026-09-13 football was re-ingested: it had been logged locally
    (no ``sync_record_id``), pushed as ``manual:2026-09-12T14:30``, and pulled
    back as a "new" record. A cheap early-out before reconstructing the draft;
    the write chokepoint dedups by ``workout_id`` as a second guard.
    """
    for day, entries in logs.items():
        for entry in entries:
            if _entry_workout_id(day, entry) == record_id:
                return True
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
    on_ingested: OnIngestedCallback | None = None,
) -> list[str]:
    """Ingest synced manual workouts into ``log.json``.

    For each ``(record_id, payload)`` tagged ``kind="manual_workout"``:
    reconstruct + re-validate the draft on the PC, enforce the rate budget, then
    HMAC-sign and APPEND it under its own ``date`` (a day may hold several
    workouts). Idempotent: dedup by ``record_id`` here and by ``workout_id`` in
    the write chokepoint, so re-syncing the same record is a no-op.

    When ``on_ingested`` is given, it's called ``on_ingested(entry, prior_entries)``
    right after each newly-appended record — ``prior_entries`` being that
    entry's own date's entries written before it — so the caller (see
    ``screen_lock.ScreenLocker._ingest_synced_manual_workouts``) can apply the
    identical live-workout shutdown/debt reward. This applies regardless of
    whether ``date`` is today or back-dated: there's only one current shutdown
    config, so a back-dated sync still pushes it exactly as a live workout
    would have that day.

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
        draft = _draft_or_report(record_id, payload)
        if draft is None:
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
        # The wire id IS the workout's id: the device that logged it minted
        # ``manual:<date>T<start>`` once, and the publisher keys on the same
        # id. Without this the chokepoint re-derived one from ``date`` +
        # start, and when the two dates disagreed (a record whose day key was
        # later corrected to the local day) the same workout landed twice
        # under two ids -- and then consumed two manual-budget slots.
        entry["workout_id"] = record_id
        result = write_signed_entry(log_file, date, entry)
        if not result.appended:
            # This is dedup working, not credit being lost: the workout is
            # already in the log under this same workout_id. It was logged at
            # warning and re-reported on every 15-minute cycle, which read like
            # a recurring fault and buried the lines that did need attention.
            _logger.info(
                "Manual record %s is already logged under the same workout_id "
                "— skipped as a duplicate (its credit is already counted)",
                record_id,
            )
            continue
        ingested.append(record_id)
        if on_ingested is not None:
            on_ingested(entry, result.prior_entries)
    return ingested
