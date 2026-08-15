"""The sick-day record and the rolling budget computed from it.

Split out of :mod:`screen_locker._sick_tracker` to keep every file under the
250-line cap. Re-exported from there, so callers and their patch targets are
unchanged.

Everything here is pure: it reads a :class:`SickHistory` already in memory.
Loading and saving that history stays in ``_sick_tracker``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from screen_locker._constants import (
    SICK_BUDGET_PER_7_DAYS,
    SICK_BUDGET_PER_30_DAYS,
    SICK_BUDGET_PER_90_DAYS,
    SICK_LOCKOUT_MULTIPLIER_PER_RECENT,
    SICK_LOCKOUT_SECONDS,
)

_logger = logging.getLogger(__name__)


@dataclass
class SickHistory:
    """Persistent sick-day bookkeeping."""

    sick_days: list[str] = field(default_factory=list)
    debt: int = 0
    commitments: dict[str, bool] = field(default_factory=dict)
    broken_commitments: list[str] = field(default_factory=list)
    justifications: list[dict[str, Any]] = field(default_factory=list)


def _today_iso() -> str:
    """Return today's date as ``YYYY-MM-DD`` (UTC)."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ``YYYY-MM-DD`` into a UTC datetime, or return None."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        _logger.warning(
            "Sick history holds an unparsable date %r (%s) — that entry is "
            "IGNORED when counting sick days",
            date_str,
            exc,
        )
        return None


def is_sick_day(history: SickHistory, *, today: str | None = None) -> bool:
    """Return True if today is recorded as a sick day."""
    today_str = today or _today_iso()
    return today_str in history.sick_days


def count_in_window(
    history: SickHistory,
    days: int,
    *,
    today: str | None = None,
) -> int:
    """Return how many ``sick_days`` fall in the trailing ``days`` window."""
    today_str = today or _today_iso()
    today_dt = _parse_iso(today_str)
    if today_dt is None:
        return 0
    cutoff = today_dt - timedelta(days=days)
    count = 0
    for entry in history.sick_days:
        parsed = _parse_iso(entry)
        if parsed is None:
            continue
        if cutoff < parsed <= today_dt:
            count += 1
    return count


def is_budget_exhausted(
    history: SickHistory,
    *,
    today: str | None = None,
) -> bool:
    """Return True if any rolling window has reached its sick budget."""
    return (
        count_in_window(history, 7, today=today) >= SICK_BUDGET_PER_7_DAYS
        or count_in_window(history, 30, today=today) >= SICK_BUDGET_PER_30_DAYS
        or count_in_window(history, 90, today=today) >= SICK_BUDGET_PER_90_DAYS
    )


def compute_lockout_seconds(
    history: SickHistory,
    *,
    today: str | None = None,
) -> int:
    """Escalating sick countdown: ``base * 2 ** recent_count_in_30d``."""
    recent = count_in_window(history, 30, today=today)
    multiplier = SICK_LOCKOUT_MULTIPLIER_PER_RECENT**recent
    return SICK_LOCKOUT_SECONDS * multiplier


def budget_summary(
    history: SickHistory,
    *,
    today: str | None = None,
) -> str:
    """One-line UI summary string for budget + debt."""
    week = count_in_window(history, 7, today=today)
    month = count_in_window(history, 30, today=today)
    quarter = count_in_window(history, 90, today=today)
    return (
        f"Sick: {week}/{SICK_BUDGET_PER_7_DAYS}w · "
        f"{month}/{SICK_BUDGET_PER_30_DAYS}m · "
        f"{quarter}/{SICK_BUDGET_PER_90_DAYS}q  ·  "
        f"Debt: {history.debt}"
    )
