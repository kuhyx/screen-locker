"""Extra benefits for exceeding the weekly workout minimum.

Tracks:
- Consecutive weeks with 5+ workouts (streak counter).
- Banked skip credits earned from extra workouts.
- ISO weeks in which the early-bird window is extended to 09:00.

State is persisted in ``extra_benefits_state.json`` next to this file.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._weekly_check import count_weekly_workouts

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_MILESTONE_INTERVAL = 4  # every 4-week streak → +1 bonus skip credit
_BONUS_THRESHOLD = 5  # workouts/week required to earn extra rewards


def _load_state(state_file: Path) -> dict[str, Any]:
    """Load benefits state, returning defaults if missing or corrupt."""
    if not state_file.exists():
        return {}
    try:
        with state_file.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state_file: Path, state: dict[str, Any]) -> None:
    """Persist benefits state to disk."""
    try:
        with state_file.open("w") as f:
            json.dump(state, f, indent=2)
    except OSError as exc:
        _logger.warning("Failed to save extra benefits state: %s", exc)


def process_week_transition(log_file: Path, state_file: Path) -> list[str]:
    """Process last week's results if we've entered a new ISO week.

    Counts workouts from the previous ISO week. If count >= 5:
    - Increments the consecutive-streak counter.
    - Awards (count - 4) skip credits.
    - Marks the *current* ISO week as having extended early-bird (09:00).
    - Awards a bonus skip credit every ``_MILESTONE_INTERVAL`` streak weeks.

    Returns a list of human-readable reward strings (empty if no transition).
    """
    now = datetime.now(tz=timezone.utc).astimezone()
    year, week, _ = now.isocalendar()
    current_week_str = f"{year}-W{week:02d}"

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
        tzinfo=timezone.utc,
    )
    prev_week_count = count_weekly_workouts(log_file, today=prev_week_dt)

    streak = int(state.get("consecutive_5plus_weeks", 0))
    skip_credits = int(state.get("skip_credits", 0))
    eb_weeks: list[str] = list(state.get("extended_early_bird_iso_weeks", []))

    rewards: list[str] = []
    prev_year, prev_week, _ = sunday_prev_week.isocalendar()
    prev_week_str = f"{prev_year}-W{prev_week:02d}"

    if prev_week_count >= _BONUS_THRESHOLD:
        extra = prev_week_count - 4
        streak += 1
        skip_credits += extra
        if current_week_str not in eb_weeks:
            eb_weeks.append(current_week_str)
        rewards.append(
            f"{prev_week_count} workouts in {prev_week_str}! "
            f"+{extra} skip credit(s), early-bird extended to 09:00 this week"
        )
        if streak % _MILESTONE_INTERVAL == 0:
            skip_credits += 1
            rewards.append(f"{streak}-week streak milestone! +1 bonus skip credit")
    else:
        if streak > 0:
            rewards.append(f"Streak reset (was {streak} weeks of 5+ workouts)")
        streak = 0

    _save_state(
        state_file,
        {
            "consecutive_5plus_weeks": streak,
            "last_processed_iso_week": current_week_str,
            "skip_credits": skip_credits,
            "extended_early_bird_iso_weeks": eb_weeks,
        },
    )
    return rewards


def current_streak(state_file: Path) -> int:
    """Return the current consecutive-5plus-weeks streak count."""
    return int(_load_state(state_file).get("consecutive_5plus_weeks", 0))


def has_skip_credit(state_file: Path) -> bool:
    """Return True if at least one banked skip credit is available."""
    return int(_load_state(state_file).get("skip_credits", 0)) > 0


def consume_skip_credit(state_file: Path) -> None:
    """Deduct one skip credit from the bank."""
    state = _load_state(state_file)
    credit_count = int(state.get("skip_credits", 0))
    if credit_count > 0:
        state["skip_credits"] = credit_count - 1
        _save_state(state_file, state)


def has_extended_early_bird(state_file: Path) -> bool:
    """Return True if the current ISO week has an extended early-bird window (09:00)."""
    now = datetime.now(tz=timezone.utc).astimezone()
    year, week, _ = now.isocalendar()
    current_week_str = f"{year}-W{week:02d}"
    eb_weeks: list[str] = _load_state(state_file).get(
        "extended_early_bird_iso_weeks", []
    )
    return current_week_str in eb_weeks
