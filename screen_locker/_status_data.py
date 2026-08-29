"""Read-only status snapshot: today, this week, shutdown projection, sick budget.

Every function in this module only reads files already on disk — no ADB, no
sudo, no network, no writes. ``_status.py`` stays untouched (it's an
existing, tested, deliberately *mutating* CLI used by a human running
``--status`` who already expects that); this module is the new, genuinely
side-effect-free layer that both the i3blocks summary line and the Tkinter
status view are built on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from screen_locker import _manual_workout
from screen_locker._compliance_state import explain_lock_decision
from screen_locker._status_projection import (
    _shutdown_projection,
    format_summary_line,
)
from screen_locker._status_types import (
    DayStatus,
    ManualWorkoutBudgetStatus,
    ShutdownProjection,
    ShutdownProjectionDay,
    SickBudgetStatus,
    StatusSnapshot,
    WeeklySummary,
)

__all__ = [
    "DayStatus",
    "ManualWorkoutBudgetStatus",
    "ShutdownProjection",
    "ShutdownProjectionDay",
    "SickBudgetStatus",
    "StatusSnapshot",
    "WeeklySummary",
    "format_summary_line",
    "gather_status",
]
from screen_locker._constants import (
    EARLY_BIRD_PENDING_FILE,
    EXTRA_BENEFITS_FILE,
    MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
    MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
    SCHEDULED_SKIPS_FILE,
    SHUTDOWN_BASE_FILE,
    SHUTDOWN_CONFIG_FILE,
    SICK_BUDGET_PER_7_DAYS,
    SICK_BUDGET_PER_30_DAYS,
    SICK_BUDGET_PER_90_DAYS,
)
from screen_locker._extra_benefits import (
    current_streak,
    has_extended_early_bird,
    weekly_shutdown_bonus_hours,
)
from screen_locker._log_io import load_workout_log
from screen_locker._sick_tracker import (
    count_in_window,
    is_budget_exhausted,
    load_history,
)
from screen_locker._wake_state import has_workout_skip_today
from screen_locker._weekly_check import (
    COUNTED_WORKOUT_TYPES,
    MANUAL_WORKOUT_TYPE,
    VERIFIED_WORKOUT_TYPES,
    WEEKLY_WORKOUT_MINIMUM,
    is_relaxed_day,
)

if TYPE_CHECKING:
    from screen_locker._sick_tracker import SickHistory

_DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "log.json"


def _day_status(day_date: date, entries: list[dict], sick_days: set[str]) -> DayStatus:
    """Build a :class:`DayStatus` for one calendar day from its entry list.

    ``day_count`` mirrors the weekly rule (each verified workout counts, all of
    a day's manual entries count once) so the week total sums to
    :func:`~screen_locker._weekly_check.count_weekly_workouts`.
    """
    iso = day_date.isoformat()
    label = day_date.strftime("%a %b %d")
    types = tuple(
        str(e.get("workout_data", {}).get("type", ""))
        for e in entries
        if isinstance(e, dict)
    )
    verified = sum(1 for t in types if t in VERIFIED_WORKOUT_TYPES)
    has_manual = any(t == MANUAL_WORKOUT_TYPE for t in types)
    sources = [
        str(e.get("workout_data", {}).get("source", ""))
        for e in entries
        if isinstance(e, dict)
    ]
    return DayStatus(
        date=iso,
        label=label,
        entry_types=tuple(t for t in types if t),
        source=" · ".join(s for s in sources if s),
        counted=any(t in COUNTED_WORKOUT_TYPES for t in types),
        day_count=verified + (1 if has_manual else 0),
        is_sick_day=iso in sick_days,
    )


def _week_days(
    log_file: Path, sick_history: SickHistory, *, today_local: datetime
) -> tuple[DayStatus, ...]:
    """Return this ISO week's days from Monday through today."""
    log_data = load_workout_log(log_file)
    sick_days = set(sick_history.sick_days)
    today_date = today_local.date()
    monday = today_date - timedelta(days=today_date.weekday())
    days: list[DayStatus] = []
    day = monday
    while day <= today_date:
        days.append(_day_status(day, log_data.get(day.isoformat(), []), sick_days))
        day += timedelta(days=1)
    return tuple(days)


def _weekly_summary(days: tuple[DayStatus, ...]) -> WeeklySummary:
    """Summarize a week's workout count against the weekly minimum."""
    counted = sum(d.day_count for d in days)
    return WeeklySummary(
        days=days,
        counted_count=counted,
        minimum=WEEKLY_WORKOUT_MINIMUM,
        remaining=max(0, WEEKLY_WORKOUT_MINIMUM - counted),
        extra=max(0, counted - WEEKLY_WORKOUT_MINIMUM),
    )


def _sick_budget_status(history: SickHistory, *, today: str) -> SickBudgetStatus:
    """Summarize rolling sick-day budget usage."""
    return SickBudgetStatus(
        used_7d=count_in_window(history, 7, today=today),
        budget_7d=SICK_BUDGET_PER_7_DAYS,
        used_30d=count_in_window(history, 30, today=today),
        budget_30d=SICK_BUDGET_PER_30_DAYS,
        used_90d=count_in_window(history, 90, today=today),
        budget_90d=SICK_BUDGET_PER_90_DAYS,
        debt=history.debt,
        exhausted=is_budget_exhausted(history, today=today),
    )


def _manual_workout_budget_status(
    log_file: Path, *, today: str
) -> ManualWorkoutBudgetStatus:
    """Summarize rolling manual-workout budget usage."""
    return ManualWorkoutBudgetStatus(
        used_7d=_manual_workout.count_in_window(log_file, 7, today=today),
        budget_7d=MANUAL_WORKOUT_BUDGET_PER_7_DAYS,
        used_30d=_manual_workout.count_in_window(log_file, 30, today=today),
        budget_30d=MANUAL_WORKOUT_BUDGET_PER_30_DAYS,
        exhausted=_manual_workout.is_budget_exhausted(log_file, today=today),
    )


def gather_status(
    *,
    log_file: Path = _DEFAULT_LOG_FILE,
    extra_benefits_file: Path = EXTRA_BENEFITS_FILE,
    shutdown_base_file: Path = SHUTDOWN_BASE_FILE,
    shutdown_config_file: Path = SHUTDOWN_CONFIG_FILE,
    scheduled_skips_file: Path = SCHEDULED_SKIPS_FILE,
    early_bird_pending_file: Path = EARLY_BIRD_PENDING_FILE,
    now: datetime | None = None,
) -> StatusSnapshot:
    """Gather a full :class:`StatusSnapshot` from on-disk state only.

    Never touches ADB, sudo, or the network — safe to call on every i3blocks
    tick and every status-window open/refresh.
    """
    instant = now if now is not None else datetime.now(tz=UTC)
    today_local = instant.astimezone()
    today_str = today_local.date().isoformat()

    sick_history = load_history()
    days = _week_days(log_file, sick_history, today_local=today_local)
    week = _weekly_summary(days)
    early_bird_extended = has_extended_early_bird(
        extra_benefits_file, today=today_local
    )

    lock_explanation = explain_lock_decision(
        log_file=log_file,
        scheduled_skips_file=scheduled_skips_file,
        early_bird_pending_file=early_bird_pending_file,
        sick_history=sick_history,
        extended_early_bird=early_bird_extended,
        weekly_minimum_met=week.counted_count >= WEEKLY_WORKOUT_MINIMUM,
        relaxed_day=is_relaxed_day(today=today_local),
        wake_skip=has_workout_skip_today(),
        now=instant,
    )

    return StatusSnapshot(
        today=days[-1],
        week=week,
        bonus_hours_this_week=weekly_shutdown_bonus_hours(
            extra_benefits_file, today=today_local
        ),
        streak=current_streak(extra_benefits_file),
        early_bird_extended=early_bird_extended,
        shutdown=_shutdown_projection(
            shutdown_base_file=shutdown_base_file,
            shutdown_config_file=shutdown_config_file,
            extra_benefits_file=extra_benefits_file,
            log_file=log_file,
            today_local=today_local,
        ),
        lock_explanation=lock_explanation,
        sick_budget=_sick_budget_status(sick_history, today=today_str),
        manual_workout_budget=_manual_workout_budget_status(log_file, today=today_str),
        generated_at=instant.isoformat(),
    )
