"""Shutdown projection and the one-line i3blocks summary.

Split out of :mod:`screen_locker._status_data` to keep every file under the
250-line cap. ``format_summary_line`` is re-exported from there, so
``status_view`` and the i3blocks CLI are unaffected.

Projects what time the PC will shut down on each remaining day of the week,
and renders the compact status line.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from screen_locker._extra_benefits import (
    current_streak,
    preview_bonus_if_week_ended_now,
    weekly_shutdown_bonus_hours,
)
from screen_locker._shutdown import read_shutdown_config
from screen_locker._shutdown_base import get_base_hours
from screen_locker._status_types import ShutdownProjection, ShutdownProjectionDay
from screen_locker._weekly_check import count_weekly_workouts

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker._status_types import StatusSnapshot

_RELAXED_DAY_EXPLANATION = (
    "Shutdown time and the screen lock are two separate systems: the lock "
    "decides whether you must log a workout right now; shutdown time only "
    "controls how late the PC stays on tonight."
)
_WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MON_WED_WEEKDAYS = frozenset({0, 1, 2})


def _week_rows(
    mon_wed_hour: int, thu_sun_hour: int, *, speculative: bool
) -> tuple[ShutdownProjectionDay, ...]:
    """Build 7 labeled rows, one per weekday, from a Mon-Wed/Thu-Sun band pair."""
    return tuple(
        ShutdownProjectionDay(
            label=label,
            hour=mon_wed_hour if weekday in _MON_WED_WEEKDAYS else thu_sun_hour,
            speculative=speculative,
        )
        for weekday, label in enumerate(_WEEKDAY_LABELS)
    )


def _shutdown_projection(
    *,
    shutdown_base_file: Path,
    shutdown_config_file: Path,
    extra_benefits_file: Path,
    log_file: Path,
    today_local: datetime,
) -> ShutdownProjection:
    """Build the shutdown-time projection: tonight, rest of week, next week."""
    tonight = read_shutdown_config(shutdown_config_file)
    base_mw, base_ts = get_base_hours(shutdown_base_file)
    bonus = weekly_shutdown_bonus_hours(extra_benefits_file, today=today_local)
    rest_of_week = _week_rows(base_mw + bonus, base_ts + bonus, speculative=False)

    this_week_count = count_weekly_workouts(log_file, today=today_local)
    streak = current_streak(extra_benefits_file)
    _would_be_streak, would_be_bonus = preview_bonus_if_week_ended_now(
        this_week_count, streak
    )
    next_week_preview = _week_rows(
        base_mw + would_be_bonus, base_ts + would_be_bonus, speculative=True
    )

    return ShutdownProjection(
        tonight=tonight,
        rest_of_week=rest_of_week,
        next_week_preview=next_week_preview,
        explanation=_RELAXED_DAY_EXPLANATION,
    )


def _tonight_hour(snapshot: StatusSnapshot) -> int | None:
    """Pick the shutdown hour band (Mon-Wed vs Thu-Sun) matching today.

    Uses ``snapshot.generated_at`` (not a fresh ``datetime.now()``) so the
    summary line is a pure function of the snapshot it was handed.
    """
    if snapshot.shutdown.tonight is None:
        return None
    mon_wed_hour, thu_sun_hour, _morning = snapshot.shutdown.tonight
    generated_weekday = (
        datetime.fromisoformat(snapshot.generated_at).astimezone().weekday()
    )
    return mon_wed_hour if generated_weekday in _MON_WED_WEEKDAYS else thu_sun_hour


def format_summary_line(snapshot: StatusSnapshot) -> str:
    """Cheap one-liner for the i3blocks summary (e.g. before/after a click)."""
    week = snapshot.week
    mark = "✓" if week.remaining == 0 else "…"
    tonight_hour = _tonight_hour(snapshot)
    tonight_str = f"{tonight_hour:02d}:00" if tonight_hour is not None else "?"
    sick = snapshot.sick_budget
    return (
        f"{mark} {week.counted_count}/{week.minimum} workouts · "
        f"{tonight_str} tonight · sick {sick.used_7d}/{sick.budget_7d}"
    )
