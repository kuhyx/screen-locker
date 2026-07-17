"""Read-only status snapshot: today, this week, shutdown projection, sick budget.

Every function in this module only reads files already on disk — no ADB, no
sudo, no network, no writes. ``_status.py`` stays untouched (it's an
existing, tested, deliberately *mutating* CLI used by a human running
``--status`` who already expects that); this module is the new, genuinely
side-effect-free layer that both the i3blocks summary line and the Tkinter
status view are built on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from screen_locker import _manual_workout
from screen_locker._compliance_state import LockExplanation, explain_lock_decision
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
    preview_bonus_if_week_ended_now,
    weekly_shutdown_bonus_hours,
)
from screen_locker._log_io import load_workout_log
from screen_locker._shutdown import read_shutdown_config
from screen_locker._shutdown_base import get_base_hours
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
    count_weekly_workouts,
    is_relaxed_day,
)

if TYPE_CHECKING:
    from screen_locker._sick_tracker import SickHistory

_DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "workout_log.json"
_RELAXED_DAY_EXPLANATION = (
    "Shutdown time and the screen lock are two separate systems: the lock "
    "decides whether you must log a workout right now; shutdown time only "
    "controls how late the PC stays on tonight."
)
_WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MON_WED_WEEKDAYS = frozenset({0, 1, 2})


@dataclass(frozen=True)
class DayStatus:
    """One day's workout outcome (a day may hold several workouts)."""

    date: str
    label: str
    entry_types: tuple[str, ...]
    source: str
    counted: bool
    day_count: int
    is_sick_day: bool


@dataclass(frozen=True)
class WeeklySummary:
    """This ISO week's workout compliance so far."""

    days: tuple[DayStatus, ...]
    counted_count: int
    minimum: int
    remaining: int
    extra: int


@dataclass(frozen=True)
class SickBudgetStatus:
    """Rolling sick-day budget usage."""

    used_7d: int
    budget_7d: int
    used_30d: int
    budget_30d: int
    used_90d: int
    budget_90d: int
    debt: int
    exhausted: bool


@dataclass(frozen=True)
class ManualWorkoutBudgetStatus:
    """Rolling manual-workout budget usage."""

    used_7d: int
    budget_7d: int
    used_30d: int
    budget_30d: int
    exhausted: bool


@dataclass(frozen=True)
class ShutdownProjectionDay:
    """One labeled row in a shutdown-time projection."""

    label: str
    hour: int
    speculative: bool


@dataclass(frozen=True)
class ShutdownProjection:
    """Tonight's live config plus deterministic/speculative week projections."""

    tonight: tuple[int, int, int] | None
    rest_of_week: tuple[ShutdownProjectionDay, ...]
    next_week_preview: tuple[ShutdownProjectionDay, ...]
    explanation: str


@dataclass(frozen=True)
class StatusSnapshot:
    """Everything the status view needs, gathered in one read-only pass."""

    today: DayStatus
    week: WeeklySummary
    bonus_hours_this_week: int
    streak: int
    early_bird_extended: bool
    shutdown: ShutdownProjection
    lock_explanation: LockExplanation
    sick_budget: SickBudgetStatus
    manual_workout_budget: ManualWorkoutBudgetStatus
    generated_at: str


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
    instant = now if now is not None else datetime.now(tz=timezone.utc)
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
