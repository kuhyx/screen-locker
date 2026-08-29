"""Manual-workout sports, the draft record, and rolling budget accounting.

Split out of :mod:`screen_locker._manual_workout` to keep every file under the
250-line cap. Everything here is re-exported from there, so callers and their
patch targets are unchanged.

The budget is what stops a manual entry from being an unlimited escape hatch:
manual workouts are self-reported, so only a few count in any rolling window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING

from screen_locker._constants import (
    MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
    MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
)
from screen_locker._log_io import load_workout_log

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
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ``YYYY-MM-DD`` into a UTC datetime, or return None."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        _logger.warning(
            "Workout log has an unparsable date key %r (%s) — that day is "
            "IGNORED when counting the manual-workout budget",
            date_str,
            exc,
        )
        return None


def count_in_window(
    log_file: Path,
    days: int,
    *,
    today: str | None = None,
) -> int:
    """Return how many ``manual_workout`` ENTRIES fall in the trailing window.

    Counted per entry, not per day: each logged manual workout consumes its
    own budget slot, matching how each one also earns its own weekly-count
    and shutdown credit (see ``screen_locker._weekly_check.COUNTED_WORKOUT_TYPES``
    and ``screen_locker._workout_credit``) — the budget is the sole limiter on
    how many you can log, not a once-per-day collapse.
    """
    today_str = today or _today_iso()
    today_dt = _parse_iso(today_str)
    if today_dt is None:
        return 0
    cutoff = today_dt - timedelta(days=days)
    count = 0
    for date_str, entries in load_workout_log(log_file).items():
        parsed = _parse_iso(date_str)
        if parsed is None or not (cutoff < parsed <= today_dt):
            continue
        count += sum(
            1
            for entry in entries
            if entry.get("workout_data", {}).get("type") == MANUAL_WORKOUT_TYPE
        )
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
    reservation_phone: str = ""
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
