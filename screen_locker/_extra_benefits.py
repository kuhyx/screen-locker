"""Extra benefits for exceeding the weekly workout minimum.

Tracks:
- Consecutive weeks with 5+ workouts (streak counter).
- Banked shutdown-time bonus hours earned from extra workouts, applied
  every day of the following week. This never reduces enforcement (unlike
  a banked "skip a workout" credit would) — it only grants extra comfort
  time on top of a floor you still have to earn each day.
- ISO weeks in which the early-bird window is extended to 09:00.

State is persisted in ``extra_benefits_state.json`` next to this file.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._weekly_check import count_weekly_workouts

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_MILESTONE_INTERVAL = 4  # every 4-week streak → +1h extra shutdown bonus
_BONUS_THRESHOLD = 5  # workouts/week required to earn extra rewards


def _load_state(state_file: Path) -> dict[str, Any]:
    """Load benefits state, returning defaults if missing or corrupt."""
    if not state_file.exists():
        return {}
    try:
        with state_file.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read extra-benefits state from %s: %s — starting from "
            "empty state, so the workout streak and any banked bonus hours are "
            "lost for this run",
            state_file,
            exc,
        )
        return {}


def _save_state(state_file: Path, state: dict[str, Any]) -> None:
    """Persist benefits state to disk."""
    try:
        with state_file.open("w") as f:
            json.dump(state, f, indent=2)
    except OSError as exc:
        _logger.warning("Failed to save extra benefits state: %s", exc)


def _current_iso_week(now: datetime) -> str:
    """Return *now*'s ISO week as ``YYYY-Www``."""
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def preview_bonus_if_week_ended_now(
    current_week_count: int, current_streak: int
) -> tuple[int, int]:
    """(would_be_new_streak, would_be_bonus_hours) if the ISO week ended now.

    Pure extraction of ``process_week_transition``'s threshold math — no file
    I/O, safe to call from a read-only status view for a "next week preview."
    """
    if current_week_count < _BONUS_THRESHOLD:
        return 0, 0
    streak = current_streak + 1
    bonus_hours = current_week_count - 4
    if streak % _MILESTONE_INTERVAL == 0:
        bonus_hours += 1
    return streak, bonus_hours


def process_week_transition(log_file: Path, state_file: Path) -> list[str]:
    """Process last week's results if we've entered a new ISO week.

    Counts workouts from the previous ISO week. If count >= 5:
    - Increments the consecutive-streak counter.
    - Banks (count - 4) hours of shutdown-time bonus for the current week,
      applied once per day on top of the daily base reset.
    - Marks the *current* ISO week as having extended early-bird (09:00).
    - Adds +1h more bonus every ``_MILESTONE_INTERVAL`` streak weeks.

    Returns a list of human-readable reward strings (empty if no transition).
    """
    now = datetime.now(tz=UTC).astimezone()
    current_week_str = _current_iso_week(now)

    state = _load_state(state_file)
    if state.get("last_processed_iso_week") == current_week_str:
        return []

    # Count workouts in the previous ISO week (Mon through Sun).
    monday_this_week = now.date() - timedelta(days=now.weekday())
    sunday_prev_week = monday_this_week - timedelta(days=1)
    prev_week_dt = datetime(
        sunday_prev_week.year,
        sunday_prev_week.month,
        sunday_prev_week.day,
        23,
        59,
        59,
        tzinfo=UTC,
    )
    prev_week_count = count_weekly_workouts(log_file, today=prev_week_dt)

    streak = int(state.get("consecutive_5plus_weeks", 0))
    weekly_bonus_hours: dict[str, int] = dict(
        state.get("weekly_shutdown_bonus_hours", {})
    )
    eb_weeks: list[str] = list(state.get("extended_early_bird_iso_weeks", []))

    rewards: list[str] = []
    prev_year, prev_week, _ = sunday_prev_week.isocalendar()
    prev_week_str = f"{prev_year}-W{prev_week:02d}"

    if prev_week_count >= _BONUS_THRESHOLD:
        extra = prev_week_count - 4
        streak, bonus_hours = preview_bonus_if_week_ended_now(prev_week_count, streak)
        if current_week_str not in eb_weeks:
            eb_weeks.append(current_week_str)
        rewards.append(
            f"{prev_week_count} workouts in {prev_week_str}! "
            f"+{extra}h shutdown bonus this week, early-bird extended to 09:00"
        )
        if streak % _MILESTONE_INTERVAL == 0:
            rewards.append(f"{streak}-week streak milestone! +1h extra shutdown bonus")
        weekly_bonus_hours[current_week_str] = bonus_hours
    else:
        if streak > 0:
            rewards.append(f"Streak reset (was {streak} weeks of 5+ workouts)")
        streak = 0

    # Merge onto the loaded state rather than rebuilding it from these four
    # keys: sibling fields written by the recovery scripts (e.g.
    # ``shutdown_bonus_granted_for``, the guard that stops a compensation
    # bonus being granted twice) live in this file too, and rebuilding would
    # drop them at the next weekly rollover — silently re-arming a double-grant.
    updated = dict(state)
    updated.update(
        {
            "consecutive_5plus_weeks": streak,
            "last_processed_iso_week": current_week_str,
            "weekly_shutdown_bonus_hours": weekly_bonus_hours,
            "extended_early_bird_iso_weeks": eb_weeks,
        }
    )
    _save_state(state_file, updated)
    return rewards


def current_streak(state_file: Path) -> int:
    """Return the current consecutive-5plus-weeks streak count."""
    return int(_load_state(state_file).get("consecutive_5plus_weeks", 0))


def weekly_shutdown_bonus_hours(
    state_file: Path, *, today: datetime | None = None
) -> int:
    """Return the banked shutdown-time bonus (hours) for the current ISO week."""
    now = today if today is not None else datetime.now(tz=UTC).astimezone()
    current_week_str = _current_iso_week(now)
    bonus_hours: dict[str, int] = _load_state(state_file).get(
        "weekly_shutdown_bonus_hours", {}
    )
    return int(bonus_hours.get(current_week_str, 0))


def has_extended_early_bird(state_file: Path, *, today: datetime | None = None) -> bool:
    """Return True if the current ISO week has an extended early-bird window (09:00)."""
    now = today if today is not None else datetime.now(tz=UTC).astimezone()
    current_week_str = _current_iso_week(now)
    eb_weeks: list[str] = _load_state(state_file).get(
        "extended_early_bird_iso_weeks", []
    )
    return current_week_str in eb_weeks
