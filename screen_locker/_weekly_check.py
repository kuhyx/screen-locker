"""Weekly workout count and day-of-week mode detection for the screen locker.

On Tue/Wed/Thu (relaxed days) the lock is optional: the user can skip
without any penalty, or voluntarily import a Stronglift workout which
will count toward the weekly minimum.

On Fri/Sat/Sun/Mon (enforced days) the lock fires unless the user has
already logged at least WEEKLY_WORKOUT_MINIMUM verified workouts in the
current ISO week (Mon-Sun).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

WEEKLY_WORKOUT_MINIMUM: int = 4

# Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
_RELAXED_WEEKDAYS: frozenset[int] = frozenset({1, 2, 3})  # Tue, Wed, Thu

# Only phone-verified workouts count toward the weekly minimum.
_COUNTED_WORKOUT_TYPES: frozenset[str] = frozenset({"phone_verified"})


def is_relaxed_day(*, today: datetime | None = None) -> bool:
    """Return True if today is a relaxed day (Tue, Wed, or Thu).

    Args:
        today: Override for the current local datetime (for testing).

    Returns:
        True when the current weekday is Tuesday, Wednesday, or Thursday.
    """
    dt = today if today is not None else datetime.now(tz=timezone.utc).astimezone()
    return dt.weekday() in _RELAXED_WEEKDAYS


def count_weekly_workouts(
    log_file: Path,
    *,
    today: datetime | None = None,
) -> int:
    """Count phone-verified workouts logged in the current ISO week (Mon-Sun).

    Args:
        log_file: Path to ``workout_log.json``.
        today: Override for the current local datetime (for testing).

    Returns:
        Number of ``phone_verified`` entries whose date falls within the
        current ISO week, up to and including today.
    """
    dt = today if today is not None else datetime.now(tz=timezone.utc).astimezone()
    week_start = (dt - timedelta(days=dt.weekday())).date()
    today_date = dt.date()

    if not log_file.exists():
        return 0
    try:
        with log_file.open() as f:
            logs: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError):
        _logger.warning("Could not read workout log for weekly count")
        return 0

    count = 0
    for date_str, entry in logs.items():
        try:
            entry_date = (
                datetime.strptime(date_str, "%Y-%m-%d")
                .replace(tzinfo=timezone.utc)
                .date()
            )
        except ValueError:
            continue
        if not (week_start <= entry_date <= today_date):
            continue
        if not isinstance(entry, dict):
            continue
        wtype = entry.get("workout_data", {}).get("type", "")
        if wtype in _COUNTED_WORKOUT_TYPES:
            count += 1
    return count


def has_weekly_minimum(
    log_file: Path,
    *,
    today: datetime | None = None,
) -> bool:
    """Return True if the weekly workout minimum has already been reached.

    Args:
        log_file: Path to ``workout_log.json``.
        today: Override for the current local datetime (for testing).

    Returns:
        True when ``count_weekly_workouts`` >= ``WEEKLY_WORKOUT_MINIMUM``.
    """
    return count_weekly_workouts(log_file, today=today) >= WEEKLY_WORKOUT_MINIMUM
