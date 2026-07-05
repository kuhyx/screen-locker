"""Manual (unverified) workout rate-limiting, validation, and entry-building.

Pure logic — no Tk imports. Unlike sick days, manual-workout entries live
directly in ``workout_log.json`` (not a separate history file): a manual
entry is just another ``workout_data`` dict with ``type="manual_workout"``,
so ``LogMixin.save_workout_log`` already HMAC-signs it for free and the
weekly-minimum/bonus logic already counts it once wired into
``COUNTED_WORKOUT_TYPES``. This module only adds the rate-budget check (by
scanning ``workout_log.json`` itself) and the evidence-form validation.

Each sport has its own structured fields (e.g. table tennis tracks
matches/sets won-lost and racket/balls, rather than one free-text blob) —
see :class:`ManualWorkoutDraft` and :data:`SPORT_CHOICES`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._constants import (
    MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
    MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
    MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS,
    MANUAL_WORKOUT_MIN_DURATION_MINUTES,
    MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
    MANUAL_WORKOUT_RPE_MAX,
    MANUAL_WORKOUT_RPE_MIN,
)

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

MANUAL_WORKOUT_TYPE = "manual_workout"

SPORT_TABLE_TENNIS = "table_tennis"
SPORT_OTHER = "other"
SPORT_CHOICES: tuple[str, ...] = (SPORT_TABLE_TENNIS, SPORT_OTHER)
SPORT_LABELS: dict[str, str] = {
    SPORT_TABLE_TENNIS: "Table tennis",
    SPORT_OTHER: "Other",
}


def _today_iso() -> str:
    """Return today's date as ``YYYY-MM-DD`` (UTC)."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ``YYYY-MM-DD`` into a UTC datetime, or return None."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_logs(log_file: Path) -> dict[str, Any]:
    """Read ``workout_log.json``. Missing or unreadable file yields ``{}``."""
    if not log_file.exists():
        return {}
    try:
        with log_file.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        _logger.warning("Could not read workout log for manual-workout budget check")
        return {}


def count_in_window(
    log_file: Path,
    days: int,
    *,
    today: str | None = None,
) -> int:
    """Return how many ``manual_workout`` entries fall in the trailing window."""
    today_str = today or _today_iso()
    today_dt = _parse_iso(today_str)
    if today_dt is None:
        return 0
    cutoff = today_dt - timedelta(days=days)
    logs = _load_logs(log_file)
    count = 0
    for date_str, entry in logs.items():
        parsed = _parse_iso(date_str)
        if parsed is None or not (cutoff < parsed <= today_dt):
            continue
        workout_data = entry.get("workout_data", {}) if isinstance(entry, dict) else {}
        if workout_data.get("type") == MANUAL_WORKOUT_TYPE:
            count += 1
    return count


def is_budget_exhausted(
    log_file: Path,
    *,
    today: str | None = None,
) -> bool:
    """Return True if either rolling window has reached its manual-workout budget."""
    return (
        count_in_window(log_file, 7, today=today) >= MANUAL_WORKOUT_BUDGET_PER_7_DAYS
        or count_in_window(log_file, 30, today=today)
        >= MANUAL_WORKOUT_BUDGET_PER_30_DAYS
    )


def budget_summary(
    log_file: Path,
    *,
    today: str | None = None,
) -> str:
    """One-line UI summary string for the manual-workout budget."""
    week = count_in_window(log_file, 7, today=today)
    month = count_in_window(log_file, 30, today=today)
    return (
        f"Manual: {week}/{MANUAL_WORKOUT_BUDGET_PER_7_DAYS}w · "
        f"{month}/{MANUAL_WORKOUT_BUDGET_PER_30_DAYS}m"
    )


@dataclass
class ManualWorkoutDraft:
    """User-supplied evidence fields for a manual (unverified) workout.

    Fields shared by every sport come first (required unless noted).
    Sport-specific fields follow, grouped by which ``sport`` they apply to —
    only the group matching ``sport`` is validated/persisted.
    """

    sport: str
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    location_name: str
    transport_method: str
    cost: str
    rpe: int
    went_well: str
    to_improve: str
    overall_feeling: str
    location_maps_link: str = ""  # optional — awkward to fill from a locked PC
    reservation_phone: str = ""
    proof_screenshot_path: str = ""  # optional — phone-oriented field
    techniques_practiced: str = ""
    warm_up_minutes: str = ""
    pain_or_injury: str = "none"
    # SPORT_TABLE_TENNIS fields
    matches_won: int = 0
    matches_lost: int = 0
    sets_won: int = 0
    sets_lost: int = 0
    racket: str = ""
    balls: str = ""
    # SPORT_OTHER fields
    activity_type_other: str = ""
    activity_details: str = ""
    equipment: str = ""


def _parse_hhmm(value: str) -> datetime | None:
    """Parse an ``HH:MM`` string into a datetime on an arbitrary fixed date."""
    try:
        return datetime.strptime(value.strip(), "%H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
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
    if duration < MANUAL_WORKOUT_MIN_DURATION_MINUTES:
        return (
            f"Session must be at least {MANUAL_WORKOUT_MIN_DURATION_MINUTES} "
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
        "location_maps_link": draft.location_maps_link.strip(),
        "transport_method": draft.transport_method.strip(),
        "cost": draft.cost.strip(),
        "reservation_phone": draft.reservation_phone.strip(),
        "proof_screenshot_path": draft.proof_screenshot_path.strip(),
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
