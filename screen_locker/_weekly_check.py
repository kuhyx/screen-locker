"""Weekly workout count and day-of-week mode detection for the screen locker.

On Tue/Wed/Thu (relaxed days) the lock is optional: the user can skip
without any penalty, or voluntarily import a Stronglift workout which
will count toward the weekly minimum.

On Fri/Sat/Sun/Mon (enforced days) the lock fires unless the user has
already logged at least WEEKLY_WORKOUT_MINIMUM verified workouts in the
current ISO week (Mon-Sun).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

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

# The two ingestion paths for ONE StrongLifts session. The phone sync writes
# ``phone_verified``; the PC session sync writes ``pc_workout_verified``. Both
# are built from the same WorkoutSession payload, so a session done once is
# recorded twice whenever both paths run -- and ``workout_id`` is
# ``"<type>:<date>"``, so the two copies get different IDs and neither dedups
# the other away. They must therefore share ONE credit slot per day.
#
# Getting this wrong is not theoretical: on 2026-08-29 the double count pushed
# two consecutive ISO weeks to 5/5 when the real totals were 4 and 3, and
# ``has_weekly_minimum`` waived enforcement for both. Nothing reported a
# problem, because 5/5 is exactly what a compliant week looks like.
STRONGLIFTS_INGESTION_TYPES: frozenset[str] = frozenset(
    {"phone_verified", PC_WORKOUT_TYPE},
)

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
    dt = today if today is not None else datetime.now(tz=UTC).astimezone()
    return dt.weekday() in _RELAXED_WEEKDAYS


def credit_key(
    date_str: str,
    entry_index: int,
    entry: Mapping[str, Any],
) -> tuple[str, str] | None:
    """Return the credit slot a log entry occupies, or None if it earns none.

    This is THE rule for "does this entry earn a workout credit, and is it the
    same credit as another entry". Every counter in the package must go through
    it rather than re-deriving the rule, because a second copy of the rule that
    drifts from this one is precisely the bug this function was written to fix.

    Args:
        date_str: The ``YYYY-MM-DD`` key the entry is filed under.
        entry_index: Position of the entry within that date's list, used to
            keep independently-earned credits distinct.
        entry: The log entry.

    Returns:
        A hashable key shared by entries that represent the same workout, or
        ``None`` when the entry earns no credit at all (a ``relaxed_day_skip``
        marker, a heat skip, an unknown type).
    """
    workout_data = entry.get("workout_data")
    wtype = workout_data.get("type", "") if isinstance(workout_data, Mapping) else ""
    if wtype not in COUNTED_WORKOUT_TYPES:
        return None
    if wtype in STRONGLIFTS_INGESTION_TYPES:
        # One session, however many paths ingested it.
        return ("stronglifts", date_str)
    # Verified runs and manual workouts are genuinely separate sessions, so
    # several on one day all count -- the manual-workout rate budget (see
    # screen_locker._manual_workout) is the anti-gaming limiter, not a collapse.
    return (wtype, f"{date_str}#{entry_index}")


def count_day_credits(date_str: str, entries: Iterable[Mapping[str, Any]]) -> int:
    """Count the distinct workout credits earned on one day.

    Args:
        date_str: The ``YYYY-MM-DD`` key the entries are filed under.
        entries: That date's log entries.

    Returns:
        The number of distinct credits, after collapsing the two StrongLifts
        ingestion paths onto one slot.
    """
    keys = {
        key
        for index, entry in enumerate(entries)
        if (key := credit_key(date_str, index, entry)) is not None
    }
    return len(keys)


def count_weekly_workouts(
    log_file: Path,
    *,
    today: datetime | None = None,
) -> int:
    """Count distinct workout credits in the current ISO week.

    Credits are decided by :func:`credit_key`: verified runs and manual
    workouts count individually, so multiple on one day all count, while the
    two StrongLifts ingestion paths share one slot per day so a single session
    recorded twice is credited once. Manual workouts are rate-limited
    separately by the manual-workout budget
    (:mod:`screen_locker._manual_workout`), not by a collapse here. Feeds both
    the weekly lock minimum (:func:`has_weekly_minimum`) and the banked bonus.

    Args:
        log_file: Path to ``log.json``.
        today: Override for the current local datetime (for testing).

    Returns:
        The weekly workout count (Mon-Sun, up to and including today).
    """
    dt = today if today is not None else datetime.now(tz=UTC).astimezone()
    week_start = (dt - timedelta(days=dt.weekday())).date()
    today_date = dt.date()

    count = 0
    for date_str, entries in load_workout_log(log_file).items():
        try:
            entry_date = (
                datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC).date()
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
        count += count_day_credits(date_str, entries)
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
