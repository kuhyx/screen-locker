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

WEEKLY_WORKOUT_MINIMUM: int = 5

# Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
_RELAXED_WEEKDAYS: frozenset[int] = frozenset({1, 2, 3})  # Tue, Wed, Thu

# A StrongLifts session performed on the PC itself (the Linux build of
# workout_app). Machine-checked exactly like ``phone_verified`` -- same
# WorkoutSession payload, same set/rep validation -- but named separately
# because there is no phone involved: writing "phone_verified" into an
# HMAC-signed log for a workout done on the desktop would make the log lie
# about its own provenance.
PC_WORKOUT_TYPE: str = "pc_workout_verified"

# VERIFIED workouts are machine-checked (a real StrongLifts session or a real
# RunnerUp run). They count toward the weekly total INDIVIDUALLY — multiple
# per day are allowed — because they can't be faked.
VERIFIED_WORKOUT_TYPES: frozenset[str] = frozenset(
    {"phone_verified", "runnerup_verified", PC_WORKOUT_TYPE},
)
# The single self-reported type. It counts toward the weekly total
# INDIVIDUALLY, same as a verified workout — the manual-workout rate budget
# (see screen_locker._manual_workout) is the anti-gaming limiter, not a
# once-per-day collapse here.
MANUAL_WORKOUT_TYPE: str = "manual_workout"
# Types that count toward the weekly minimum *and* are eligible for the base
# shutdown-time bonus (see screen_lock._try_adjust_shutdown_for_workout).
# Exported (no leading underscore) so other modules share this single source
# of truth instead of duplicating the type check.
COUNTED_WORKOUT_TYPES: frozenset[str] = VERIFIED_WORKOUT_TYPES | {MANUAL_WORKOUT_TYPE}

# Marks a relaxed day (Tue/Wed/Thu) as dismissed via "Skip — No Penalty" for
# the rest of the calendar day. Deliberately NOT in COUNTED_WORKOUT_TYPES —
# it's a UI-dismissal marker, not a workout, same treatment as heat_skip.
RELAXED_DAY_SKIP_TYPE: str = "relaxed_day_skip"


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
    """Count counted workouts in the current ISO week.

    Every entry whose type is in :data:`COUNTED_WORKOUT_TYPES` — verified or
    manual — counts individually, so multiple workouts on one day all count.
    Manual workouts are rate-limited separately by the manual-workout budget
    (:mod:`screen_locker._manual_workout`), not by a once-per-day collapse
    here. Feeds both the weekly lock minimum (:func:`has_weekly_minimum`) and
    the banked bonus.

    Args:
        log_file: Path to ``log.json``.
        today: Override for the current local datetime (for testing).

    Returns:
        The weekly workout count (Mon-Sun, up to and including today).
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
        for entry in entries:
            wtype = entry.get("workout_data", {}).get("type", "")
            if wtype in COUNTED_WORKOUT_TYPES:
                count += 1  # each counted workout — verified or manual — counts
    return count


def has_weekly_minimum(
    log_file: Path,
    *,
    today: datetime | None = None,
) -> bool:
    """Return True if the weekly workout minimum has already been reached.

    Args:
        log_file: Path to ``log.json``.
        today: Override for the current local datetime (for testing).

    Returns:
        True when ``count_weekly_workouts`` >= ``WEEKLY_WORKOUT_MINIMUM``.
    """
    return count_weekly_workouts(log_file, today=today) >= WEEKLY_WORKOUT_MINIMUM
