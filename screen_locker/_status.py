"""Non-locking status view: workout count, bonuses, RunnerUp scan trigger."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
import logging
import sys
from typing import TYPE_CHECKING

from screen_locker._constants import EXTRA_BENEFITS_FILE
from screen_locker._decision_log import record_no_decision
from screen_locker._earned import hhmm
from screen_locker._extra_benefits import (
    current_streak,
    has_extended_early_bird,
)
from screen_locker._log_io import load_workout_log
from screen_locker._sick import workout_standdown_dates
from screen_locker._weekly_check import (
    COUNTED_WORKOUT_TYPES,
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
)

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker.screen_lock import ScreenLocker

_logger = logging.getLogger(__name__)


def _load_extra_benefits() -> dict:
    """Load extra_benefits_state.json, returning {} on any error."""
    if not EXTRA_BENEFITS_FILE.exists():
        return {}
    try:
        return json.loads(EXTRA_BENEFITS_FILE.read_text())
    except (OSError, ValueError) as exc:
        _logger.warning(
            "Could not read extra-benefits state from %s: %s — the status view "
            "will show a 0 streak, which may be wrong",
            EXTRA_BENEFITS_FILE,
            exc,
        )
        return {}


def _print_day_line(d: date, entries: list[dict], sick_days: frozenset[date]) -> bool:
    """Print one day's status line(s). Returns True if any workout counted.

    A day may hold several workouts — each is printed on its own line.
    """
    label = d.strftime("%a %b %d")
    if not entries:
        if d in sick_days:
            print(f"  {label}  ✗  sick_day")
        else:
            print(f"  {label}  —  no entry")
        return False
    any_counted = False
    for entry in entries:
        wtype = entry.get("workout_data", {}).get("type", "?")
        src = entry.get("workout_data", {}).get("source", "")
        counted = wtype in COUNTED_WORKOUT_TYPES
        any_counted = any_counted or counted
        src_str = f"  ({src[:45]})" if src else ""
        mark = "✓" if counted else "✗"
        print(f"  {label}  {mark}  {wtype}{src_str}")
    return any_counted


def _scan_runnerup(locker: ScreenLocker, log_file: Path, before_count: int) -> int:
    """Run the RunnerUp week scan, print what it filled, return the new count.

    Each fill is credited by the shared ingestion callback (+2h first counted
    workout of its day, +1h each further one), the same rule the timer's sync
    pass and the daily base reset use.
    """
    n_filled = locker._scan_and_fill_week_runnerup(
        log_file, on_ingested=locker._credit_ingested_workout
    )
    locker.workout_data = {}
    if n_filled <= 0:
        print("  No new workouts found via RunnerUp scan.")
        return before_count
    print(f"  Auto-filled {n_filled} workout(s) from RunnerUp exports.")
    _, thu_sun, _ = locker._read_shutdown_config() or (None, None, None)
    if thu_sun is not None:
        print(f"  Shutdown tonight: {hhmm(thu_sun)}.")
    return count_weekly_workouts(log_file)


def _heat_skips_this_month(log_data: dict[str, list[dict]]) -> str:
    """One-line summary of this month's heat skips: count and the latest."""
    this_month = datetime.now(tz=UTC).astimezone().date().strftime("%Y-%m")
    heat_entries = [
        (d, entry)
        for d, entries in log_data.items()
        if d.startswith(this_month)
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("workout_data", {}).get("type") == "heat_skip"
    ]
    if not heat_entries:
        return "0"
    last_date, last_e = max(heat_entries, key=lambda de: de[0])
    last_temp = last_e.get("workout_data", {}).get("temperature_celsius", "?")
    return f"{len(heat_entries)} (last: {last_date}, {last_temp}°C)"


def _print_minimum(after_count: int) -> None:
    """Print how far the weekly count is from (or past) the minimum."""
    remaining = max(0, WEEKLY_WORKOUT_MINIMUM - after_count)
    extra = max(0, after_count - WEEKLY_WORKOUT_MINIMUM)
    if remaining > 0:
        print(
            f"  Need {remaining} more to reach the minimum ({WEEKLY_WORKOUT_MINIMUM})."
        )
    elif extra > 0:
        print(f"  {after_count}/{WEEKLY_WORKOUT_MINIMUM} — {extra} above minimum!")
    else:
        print(
            f"  Weekly minimum met exactly"
            f" ({WEEKLY_WORKOUT_MINIMUM}/{WEEKLY_WORKOUT_MINIMUM})."
        )


def run_status(locker: ScreenLocker) -> None:
    """Print weekly workout status, run RunnerUp scan, apply bonus, then exit."""
    today = datetime.now(tz=UTC).astimezone().date()
    monday = today - timedelta(days=today.weekday())
    log_file: Path = locker.log_file
    log_data = load_workout_log(log_file)
    sick_days = workout_standdown_dates()

    print("=== Weekly Workout Status ===")
    for i in range(7):
        d = monday + timedelta(days=i)
        if d > today:
            break
        _print_day_line(d, log_data.get(d.isoformat(), []), sick_days)
    print()

    after_count = _scan_runnerup(locker, log_file, count_weekly_workouts(log_file))
    print()

    eb_ext = has_extended_early_bird(EXTRA_BENEFITS_FILE)
    print(f"  Streak (5+ wks)     : {current_streak(EXTRA_BENEFITS_FILE)}")
    print(f"  Early-bird extended : {'Yes — until 09:00' if eb_ext else 'No'}")
    print(f"  Heat skips (month)  : {_heat_skips_this_month(log_data)}")
    print()

    _print_minimum(after_count)

    cfg = locker._read_shutdown_config()
    if cfg:
        print(f"  Shutdown tonight    : {hhmm(cfg[0])}")

    record_no_decision("--status")
    sys.exit(0)
