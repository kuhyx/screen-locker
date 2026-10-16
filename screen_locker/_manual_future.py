"""Future-dated manual workouts: the date rule and the per-date budget rule.

A manual workout may be logged AHEAD of time (``today .. today + 7 days``, never
a past date) and earns its normal credit on that date, not before. Two pure
rules live here, shared by every entry point (Tk dialog, CLI, sync ingest):

* :func:`validate_workout_date` -- the one 0..7-days-ahead check;
* :func:`budget_error_for_date` -- the rolling budget (2 per 7 days, 10 per 30)
  counted against the WORKOUT's date, over logged credits AND pending future
  entries, so a future entry holds its slot from the moment it is logged.

No I/O beyond reading ``log.json``; the pending ledger and the Firebase pull
are in ``_manual_pending`` / ``_manual_schedule``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import logging
from typing import TYPE_CHECKING

from screen_locker._constants import (
    MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
    MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
    MANUAL_WORKOUT_MAX_DAYS_AHEAD,
)
from screen_locker._day import today_str
from screen_locker._manual_workout_types import manual_credit_dates

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = [
    "BudgetUsage",
    "budget_closed_for_all_days",
    "budget_error_for_date",
    "budget_usage_for_date",
    "is_future_date",
    "parse_workout_date",
    "validate_workout_date",
]

_logger = logging.getLogger(__name__)

# (window length in days, cap) -- a window of N days is [start, start + N - 1].
_WINDOWS: tuple[tuple[int, int], ...] = (
    (7, MANUAL_WORKOUT_BUDGET_PER_7_DAYS),
    (30, MANUAL_WORKOUT_BUDGET_PER_30_DAYS),
)


def parse_workout_date(value: str) -> date | None:
    """Parse a strict ``YYYY-MM-DD`` string, or return None (and warn)."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC).date()
    except ValueError as exc:
        _logger.warning(
            "Date %r is not YYYY-MM-DD (%s) — treated as invalid", value, exc
        )
        return None


def is_future_date(value: str, *, today: str | None = None) -> bool:
    """True if ``value`` is a valid date strictly after today (local day)."""
    parsed = parse_workout_date(value)
    reference = parse_workout_date(today or today_str())
    return parsed is not None and reference is not None and parsed > reference


def validate_workout_date(value: str, *, today: str | None = None) -> str | None:
    """Return an error message if ``value`` is not today..today+7 days, else None.

    THE date rule for manual workouts: no past dates (a back-dated entry is the
    easiest way to fake a missed week) and no more than
    ``MANUAL_WORKOUT_MAX_DAYS_AHEAD`` days ahead.
    """
    parsed = parse_workout_date(value)
    if parsed is None:
        return "Workout date must be YYYY-MM-DD"
    reference = parse_workout_date(today or today_str())
    if reference is None:
        return f"Today's date {today!r} is not YYYY-MM-DD"
    ahead = (parsed - reference).days
    if ahead < 0:
        return (
            f"Workout date {value.strip()} is in the past -- only today or up "
            f"to {MANUAL_WORKOUT_MAX_DAYS_AHEAD} days ahead"
        )
    if ahead > MANUAL_WORKOUT_MAX_DAYS_AHEAD:
        return (
            f"Workout date {value.strip()} is {ahead} days ahead -- at most "
            f"{MANUAL_WORKOUT_MAX_DAYS_AHEAD} days"
        )
    return None


def _ordinals(dates: Iterable[str]) -> list[int]:
    """Day ordinals of every parsable date; unparsable ones are skipped."""
    days: list[int] = []
    for value in dates:
        parsed = parse_workout_date(value)
        if parsed is not None:
            days.append(parsed.toordinal())
    return days


def _fullest_window(days: list[int], ordinal: int, length: int) -> tuple[int, int]:
    """Return ``(count, start)`` of the fullest ``length``-day window holding D.

    Counts the entries in ``days`` only (the new entry is not among them), over
    every window ``[start, start + length - 1]`` that contains ``ordinal``.
    """
    return max(
        (
            (sum(1 for day in days if start <= day < start + length), start)
            for start in range(ordinal - length + 1, ordinal + 1)
        ),
        key=lambda found: found[0],
    )


def _existing_days(log_file: Path, pending_dates: Iterable[str]) -> list[int]:
    """Ordinals of every logged credit and every pending future entry."""
    return [*_ordinals(manual_credit_dates(log_file)), *_ordinals(pending_dates)]


@dataclass(frozen=True)
class BudgetUsage:
    """How full the fullest windows around one workout date already are."""

    week: int
    month: int

    @property
    def exhausted(self) -> bool:
        """True if one more entry on that date would break either cap."""
        return (
            self.week >= MANUAL_WORKOUT_BUDGET_PER_7_DAYS
            or self.month >= MANUAL_WORKOUT_BUDGET_PER_30_DAYS
        )


def budget_usage_for_date(
    log_file: Path,
    workout_date: str,
    pending_dates: Iterable[str] = (),
) -> BudgetUsage | None:
    """Return the fullest 7- and 30-day windows containing ``workout_date``.

    The PC's admission rule as numbers: the shared cross-language fixture
    (``fixtures/manual_budget_merge.json``, ``planned.expected_by_date``) pins
    these to what the phone computes. None if the date does not parse.
    """
    target = parse_workout_date(workout_date)
    if target is None:
        return None
    days = _existing_days(log_file, pending_dates)
    ordinal = target.toordinal()
    return BudgetUsage(
        week=_fullest_window(days, ordinal, 7)[0],
        month=_fullest_window(days, ordinal, 30)[0],
    )


def budget_error_for_date(
    log_file: Path,
    workout_date: str,
    pending_dates: Iterable[str] = (),
) -> str | None:
    """Return why a manual workout dated ``workout_date`` does not fit, else None.

    Adding an entry dated D is allowed only if EVERY rolling window containing
    D -- each 7-day window and each 30-day window -- stays within its cap
    counting the credits already in ``log_file``, the pending future entries
    in ``pending_dates``, and the new entry itself. Counting against D rather
    than against today is what lets a full week still schedule next week, and
    what keeps tomorrow's entry from being free of the cap.

    ``pending_dates`` must already exclude the entry being checked (an entry
    that holds its slot would otherwise reject itself on its own date).
    """
    target = parse_workout_date(workout_date)
    if target is None:
        return f"Workout date {workout_date!r} must be YYYY-MM-DD"
    days = _existing_days(log_file, pending_dates)
    for length, cap in _WINDOWS:
        used, start = _fullest_window(days, target.toordinal(), length)
        if used >= cap:
            first = date.fromordinal(start)
            last = first + timedelta(days=length - 1)
            return (
                f"Manual-workout budget: {used} already counted/scheduled "
                f"between {first} and {last}, max {cap} per {length} days"
            )
    return None


def budget_closed_for_all_days(
    log_file: Path,
    pending_dates: Iterable[str] = (),
    *,
    today: str | None = None,
) -> bool:
    """True if no date in today..today+7 could take another manual workout.

    The "Log Manual Workout" button hides only then; "today's window is full"
    no longer closes it, since a later day may still have room.
    """
    reference = parse_workout_date(today or today_str())
    if reference is None:
        _logger.warning("Today %r is not YYYY-MM-DD -- budget treated as closed", today)
        return True
    pending = list(pending_dates)
    return all(
        budget_error_for_date(
            log_file, (reference + timedelta(days=offset)).isoformat(), pending
        )
        is not None
        for offset in range(MANUAL_WORKOUT_MAX_DAYS_AHEAD + 1)
    )
