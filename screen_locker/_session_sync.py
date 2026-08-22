"""Ingesting synced StrongLifts sessions into ``log.json``.

The manual-workout half of sync (``_manual_sync``) has always run headlessly
from ``workout-sync.timer``. Sessions did not: ``pull_synced_workout`` was
reachable only from the interactive verification flow, so a finished session
sat in Firebase uncredited until the locker next opened a window. That was
survivable while the phone was the only device recording sessions -- the same
lock screen that asked for the workout also verified it -- but the Linux build
finishes sessions with no lock screen involved at all.

Mirrors :mod:`screen_locker._manual_sync`: reconstruct, re-validate on the PC,
then HMAC-sign and append under the session's own date. Never trusts the
record's own claim that it succeeded.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from screen_locker._constants import (
    MIN_WORKOUT_DURATION_MINUTES,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)
from screen_locker._log_mixin import write_signed_entry
from screen_locker._weekly_check import PC_WORKOUT_TYPE

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    from screen_locker._log_mixin import RecordResult

    OnIngestedCallback = Callable[[dict, "list[dict]"], None]

_logger = logging.getLogger(__name__)


def validate_session(payload: Mapping[str, object]) -> tuple[bool, str]:
    """Check a synced session payload is a real, long-enough workout.

    Deliberately re-runs the same content checks
    ``PhoneVerificationMixin._validate_json_content`` applies, rather than
    trusting ``succeeded``: a record arrives over the network and the PC is
    the thing handing out unlock credit, so it re-derives the verdict.

    Returns ``(ok, reason)``; ``reason`` always reads like a sentence so a
    rejected session says why instead of silently not counting.
    """
    exercises = payload.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        return False, "no exercises in the session payload"
    raw_duration = payload.get("duration_seconds", 0)
    if not isinstance(raw_duration, (int, float)):
        return False, f"duration_seconds is not a number: {raw_duration!r}"
    duration_min = raw_duration / 60.0
    # Accept bar carries the hidden leeway; the message advertises the round
    # number only (see _constants.py).
    if duration_min < WORKOUT_DURATION_ACCEPT_MINUTES:
        # Truncate rather than round: 34m59s rounds UP to "35 min", which is
        # exactly the hidden accept bar and would tell the user the real
        # threshold while rejecting them at it. The advertised number stays
        # MIN_WORKOUT_DURATION_MINUTES (see _constants.py).
        return False, (
            f"only {int(duration_min)} min logged, "
            f"need at least {MIN_WORKOUT_DURATION_MINUTES} min"
        )
    return True, f"{duration_min:.0f} min"


def build_session_entry(payload: Mapping[str, object], detail: str) -> dict[str, str]:
    """Build the ``workout_data`` for a verified synced session."""
    flag = "all succeeded" if payload.get("succeeded") else "partial"
    workout_type = payload.get("workout_type", "?")
    return {
        "type": PC_WORKOUT_TYPE,
        "source": f"StrongLifts workout {workout_type} ({detail}, {flag})",
        "duration_minutes": f"{float(payload.get('duration_seconds', 0)) / 60.0:.1f}",
        "sync_record_id": str(payload.get("start_time", "")),
    }


def ingest_session_records(
    log_file: Path,
    records: Iterable[tuple[str, Mapping[str, object]]],
    *,
    on_ingested: OnIngestedCallback | None = None,
) -> list[str]:
    """Ingest synced StrongLifts sessions into ``log.json``.

    For each ``(record_id, payload)``: re-validate on the PC, then HMAC-sign
    and APPEND under the session's own ``date`` so the weekly count places it
    in the right ISO week. Idempotent -- the write chokepoint dedups by
    ``workout_id`` -- so re-syncing the same session every 15 minutes is a
    no-op rather than repeated credit.

    ``on_ingested(entry, prior_entries)`` fires for each newly-appended
    session so the caller applies the identical live-workout reward.

    Returns the record ids actually ingested.
    """
    ingested: list[str] = []
    for record_id, payload in records:
        date = payload.get("date")
        if not isinstance(date, str) or not date:
            _logger.warning(
                "Skipping synced session %s: no usable date field (%r), so it "
                "cannot be filed in a week and will never count.",
                record_id,
                date,
            )
            continue
        ok, detail = validate_session(payload)
        if not ok:
            _logger.warning(
                "Skipping synced session %s dated %s: %s — it does NOT count "
                "toward the weekly minimum.",
                record_id,
                date,
                detail,
            )
            continue
        entry = build_session_entry(payload, detail)
        result: RecordResult = write_signed_entry(log_file, date, entry)
        if not result.appended:
            continue
        ingested.append(record_id)
        if on_ingested is not None:
            on_ingested(entry, result.prior_entries)
    return ingested
