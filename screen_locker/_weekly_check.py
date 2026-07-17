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
import logging
from typing import TYPE_CHECKING

from screen_locker._log_io import load_workout_log

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

WEEKLY_WORKOUT_MINIMUM: int = 4

# Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
_RELAXED_WEEKDAYS: frozenset[int] = frozenset({1, 2, 3})  # Tue, Wed, Thu

# VERIFIED workouts are machine-checked (a real StrongLifts session or a real
# RunnerUp run). They count toward the weekly total INDIVIDUALLY — multiple
# per day are allowed — because they can't be faked.
VERIFIED_WORKOUT_TYPES: frozenset[str] = frozenset(
    {"phone_verified", "runnerup_verified"},
)
# The single self-reported type. It counts at most ONCE per day (see
# count_weekly_workouts) so it can't be used to inflate the weekly total.
MANUAL_WORKOUT_TYPE: str = "manual_workout"
# Types that count toward the weekly minimum *and* are eligible for the base
# shutdown-time bonus (see screen_lock._try_adjust_shutdown_for_workout).
# Exported (no leading underscore) so other modules share this single source
# of truth instead of duplicating the type check.
COUNTED_WORKOUT_TYPES: frozenset[str] = VERIFIED_WORKOUT_TYPES | {MANUAL_WORKOUT_TYPE}


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
    """Count counted workouts in the current ISO week under the anti-gaming rule.

    Each VERIFIED workout (:data:`VERIFIED_WORKOUT_TYPES`) counts individually,
    so multiple real workouts on one day all count. Self-reported
    ``manual_workout`` entries count at most ONCE per day, so they can't inflate
    the total. Feeds both the weekly lock minimum (:func:`has_weekly_minimum`)
    and the banked bonus.

    Args:
        log_file: Path to ``workout_log.json``.
        today: Override for the current local datetime (for testing).

    Returns:
        The weekly workout count (Mon-Sun, up to and including today) under the
        verified-stack / manual-once-per-day rule.
    """
    dt = today if today is not None else datetime.now(tz=timezone.utc).astimezone()
    week_start = (dt - timedelta(days=dt.weekday())).date()
    today_date = dt.date()

    count = 0
    for date_str, entries in load_workout_log(log_file).items():
        try:
            entry_date = (
                datetime.strptime(date_str, "%Y-%m-%d")
                .replace(tzinfo=timezone.utc)
                .date()
            )
        except ValueError as exc:
            _logger.warning(
                "Workout log has an unparsable date key %r (%s) — its workouts "
                "are NOT counted toward this week's total",
                date_str,
                exc,
            )
            continue
        if not (week_start <= entry_date <= today_date):
            continue
        has_manual = False
        for entry in entries:
            wtype = entry.get("workout_data", {}).get("type", "")
            if wtype in VERIFIED_WORKOUT_TYPES:
                count += 1  # each verified workout counts
            elif wtype == MANUAL_WORKOUT_TYPE:
                has_manual = True
        if has_manual:
            count += 1  # all of a day's manual entries count as one
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
