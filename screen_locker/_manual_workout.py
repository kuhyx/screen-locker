"""Manual (unverified) workout rate-limiting, validation, and entry-building.

Pure logic — no Tk imports. Unlike sick days, manual-workout entries live
directly in ``log.json`` (not a separate history file): a manual
entry is just another ``workout_data`` dict with ``type="manual_workout"``,
so ``LogMixin.save_workout_log`` already HMAC-signs it for free and the
weekly-minimum/bonus logic already counts it once wired into
``COUNTED_WORKOUT_TYPES``. This module only adds the rate-budget check (by
scanning ``log.json`` itself) and the evidence-form validation.

Each sport has its own structured fields (e.g. table tennis tracks
matches/sets won-lost and racket/balls, rather than one free-text blob) —
see :class:`ManualWorkoutDraft` and :data:`SPORT_CHOICES`.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from screen_locker._constants import (
    MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS,
    MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    MANUAL_WORKOUT_RPE_MAX,
    MANUAL_WORKOUT_RPE_MIN,
    MIN_WORKOUT_DURATION_MINUTES,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)
from screen_locker._manual_workout_types import (
    MANUAL_WORKOUT_TYPE,
    SPORT_CHOICES,
    SPORT_LABELS,
    SPORT_OTHER,
    SPORT_TABLE_TENNIS,
    ManualWorkoutDraft,
    budget_summary,
    count_in_window,
    is_budget_exhausted,
)

__all__ = [
    "MANUAL_WORKOUT_TYPE",
    "SPORT_CHOICES",
    "SPORT_LABELS",
    "SPORT_OTHER",
    "SPORT_TABLE_TENNIS",
    "ManualWorkoutDraft",
    "budget_summary",
    "build_entry",
    "build_sync_payload",
    "count_in_window",
    "is_budget_exhausted",
    "manual_sync_record_id",
    "validate_manual_workout",
]

_logger = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> datetime | None:
    """Parse an ``HH:MM`` string into a datetime on an arbitrary fixed date."""
    try:
        return datetime.strptime(value.strip(), "%H:%M").replace(tzinfo=UTC)
    except ValueError as exc:
        _logger.warning(
            "Manual workout time %r is not HH:MM (%s) — the workout's duration "
            "cannot be computed, so the draft will fail validation",
            value,
            exc,
        )
        return None


def _duration_minutes(draft: ManualWorkoutDraft) -> float | None:
    """Return ``end_time - start_time`` in minutes, or None if unparsable."""
    start = _parse_hhmm(draft.start_time)
    end = _parse_hhmm(draft.end_time)
    if start is None or end is None or end <= start:
        return None
    return (end - start).total_seconds() / 60


def validate_manual_workout(draft: ManualWorkoutDraft) -> str | None:
    """Return an error message if the draft is invalid, else None."""
    if draft.sport not in SPORT_CHOICES:
        return "Please choose a sport"

    required = {
        "Start time": draft.start_time,
        "End time": draft.end_time,
        "Location name": draft.location_name,
        "Transport method": draft.transport_method,
        "Cost": draft.cost,
    }
    for label, value in required.items():
        if not value.strip():
            return f"{label} is required"

    duration = _duration_minutes(draft)
    if duration is None:
        return "Start/end time must be valid HH:MM, with end after start"
    # Accept bar carries the hidden leeway; the message advertises the round
    # number only (see _constants.py).
    if duration < WORKOUT_DURATION_ACCEPT_MINUTES:
        return (
            f"Session must be at least {MIN_WORKOUT_DURATION_MINUTES} "
            f"minutes (currently {duration:.0f})"
        )

    if not MANUAL_WORKOUT_RPE_MIN <= draft.rpe <= MANUAL_WORKOUT_RPE_MAX:
        return (
            f"RPE must be between {MANUAL_WORKOUT_RPE_MIN} and {MANUAL_WORKOUT_RPE_MAX}"
        )

    if draft.sport == SPORT_TABLE_TENNIS:
        error = _validate_table_tennis(draft)
    else:
        error = _validate_other_sport(draft)
    if error is not None:
        return error

    for label, value in (
        ("What went well", draft.went_well),
        ("What to improve", draft.to_improve),
        ("Overall feeling", draft.overall_feeling),
    ):
        if len(value.strip()) < MANUAL_WORKOUT_REFLECTION_MIN_CHARS:
            return (
                f"{label} must be at least {MANUAL_WORKOUT_REFLECTION_MIN_CHARS} "
                f"characters (currently {len(value.strip())})"
            )

    return None


def _validate_table_tennis(draft: ManualWorkoutDraft) -> str | None:
    """Validate the table-tennis-specific fields of a draft."""
    for label, value in (
        ("Matches won", draft.matches_won),
        ("Matches lost", draft.matches_lost),
        ("Sets won", draft.sets_won),
        ("Sets lost", draft.sets_lost),
    ):
        if value < 0:
            return f"{label} cannot be negative"
    if draft.matches_won + draft.matches_lost == 0:
        return "Enter at least one match played (won + lost)"
    if not draft.racket.strip():
        return "Racket is required"
    if not draft.balls.strip():
        return "Balls are required"
    return None


def _validate_other_sport(draft: ManualWorkoutDraft) -> str | None:
    """Validate the generic "other sport" fields of a draft."""
    if not draft.activity_type_other.strip():
        return "Activity type is required"
    if len(draft.activity_details.strip()) < MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS:
        return (
            "What was done must be at least "
            f"{MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS} characters "
            f"(currently {len(draft.activity_details.strip())})"
        )
    return None


def build_entry(draft: ManualWorkoutDraft) -> dict[str, object]:
    """Convert a validated draft into a ``workout_data`` dict for the log."""
    duration = _duration_minutes(draft)
    if draft.sport == SPORT_TABLE_TENNIS:
        activity_label = "table tennis"
    else:
        activity_label = draft.activity_type_other.strip()

    entry: dict[str, object] = {
        "type": MANUAL_WORKOUT_TYPE,
        "source": f"{activity_label} at {draft.location_name.strip()}",
        "sport": draft.sport,
        "activity_type": activity_label,
        "start_time": draft.start_time.strip(),
        "end_time": draft.end_time.strip(),
        "duration_minutes": f"{duration:.1f}" if duration is not None else "",
        "location_name": draft.location_name.strip(),
        "transport_method": draft.transport_method.strip(),
        "cost": draft.cost.strip(),
        "reservation_phone": draft.reservation_phone.strip(),
        "rpe": int(draft.rpe),
        "techniques_practiced": draft.techniques_practiced.strip(),
        "warm_up_minutes": draft.warm_up_minutes.strip(),
        "pain_or_injury": draft.pain_or_injury.strip(),
        "went_well": draft.went_well.strip(),
        "to_improve": draft.to_improve.strip(),
        "overall_feeling": draft.overall_feeling.strip(),
    }
    if draft.sport == SPORT_TABLE_TENNIS:
        entry.update(
            {
                "matches_won": int(draft.matches_won),
                "matches_lost": int(draft.matches_lost),
                "sets_won": int(draft.sets_won),
                "sets_lost": int(draft.sets_lost),
                "racket": draft.racket.strip(),
                "balls": draft.balls.strip(),
            }
        )
    else:
        entry.update(
            {
                "activity_details": draft.activity_details.strip(),
                "equipment": draft.equipment.strip(),
            }
        )
    return entry


# ── Cross-device sync wire format ─────────────────────────────────────────────
# The value of the record ``kind`` discriminator equals ``MANUAL_WORKOUT_TYPE``
# by design: on the wire a manual record is tagged ``kind="manual_workout"`` and
# its payload also carries ``type="manual_workout"``. A StrongLifts session
# payload has no ``kind`` field, so an ingesting PC routes on ``kind`` first and
# a manual record can never be mistaken for (or stamped as) a verified session.
MANUAL_WORKOUT_SYNC_KIND = MANUAL_WORKOUT_TYPE


def manual_sync_record_id(date: str, start_time: str) -> str:
    """Return the stable crdt_sync record id for a manual workout.

    Prefixed ``manual:`` so it never collides with the bare-ISO session ids the
    phone app writes into the same device log. Derived only from
    ``(date, start_time)`` so re-syncing the same workout is idempotent — this
    id must never be re-minted for a given workout.
    """
    return f"manual:{date}T{start_time.strip()}"


def build_sync_payload(draft: ManualWorkoutDraft, date: str) -> dict[str, object]:
    """Build the cross-device sync payload for a manual workout.

    This is the wire contract shared with the phone app: the same fields as
    :func:`build_entry` (what lands in ``log.json``), plus a ``kind``
    discriminator and the workout's own ``date``. ``log.json`` is
    day-keyed on the PC, but the synced payload must carry its date so the
    shared budget can be windowed and the entry filed in the right ISO week on
    ingest.
    """
    payload = build_entry(draft)
    payload["kind"] = MANUAL_WORKOUT_SYNC_KIND
    payload["date"] = date
    return payload
