"""Non-locking status view: workout count, bonuses, RunnerUp scan trigger."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import logging
import sys
from typing import TYPE_CHECKING

from screen_locker._constants import EXTRA_BENEFITS_FILE
from screen_locker._extra_benefits import (
    current_streak,
    has_extended_early_bird,
    weekly_shutdown_bonus_hours,
)
from screen_locker._log_io import load_workout_log
from screen_locker._sick_tracker import load_history
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
            "will show a 0 streak and no bonus hours, which may be wrong",
            EXTRA_BENEFITS_FILE,
            exc,
        )
        return {}


def _print_day_line(d: date, entries: list[dict], sick_days: set[str]) -> bool:
    """Print one day's status line(s). Returns True if any workout counted.

    A day may hold several workouts — each is printed on its own line.
    """
    label = d.strftime("%a %b %d")
    if not entries:
        if d.isoformat() in sick_days:
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


def run_status(locker: ScreenLocker) -> None:
    """Print weekly workout status, run RunnerUp scan, apply bonus, then exit."""
    today = datetime.now(tz=timezone.utc).astimezone().date()
    monday = today - timedelta(days=today.weekday())
    log_file: Path = locker.log_file
    log_data = load_workout_log(log_file)
    sick_days = set(load_history().sick_days)

    print("=== Weekly Workout Status ===")

    # Per-day breakdown
    for i in range(7):
        d = monday + timedelta(days=i)
        if d > today:
            break
        _print_day_line(d, log_data.get(d.isoformat(), []), sick_days)

    print()

    # The weekly total, per the anti-gaming rule (each verified workout counts
    # individually, manual counts once/day) — NOT a per-day checkmark count,
    # which would undercount a day holding two verified workouts.
    before_count = count_weekly_workouts(log_file)

    # RunnerUp scan
    n_filled = locker._scan_and_fill_week_runnerup(log_file)
    if n_filled > 0:
        print(f"  Auto-filled {n_filled} workout(s) from RunnerUp exports.")
        after_count = count_weekly_workouts(log_file)
        bonus = max(0, after_count - max(WEEKLY_WORKOUT_MINIMUM, before_count))
        if bonus > 0:
            ok = locker._adjust_shutdown_time_by(bonus)
            if ok:
                print(f"  +{bonus}h shutdown bonus applied.")
            else:
                print(f"  +{bonus}h shutdown bonus pending (config write failed).")
    else:
        print("  No new workouts found via RunnerUp scan.")
        after_count = before_count

    print()

    # Extra benefits summary
    bonus_hours = weekly_shutdown_bonus_hours(EXTRA_BENEFITS_FILE)
    streak = current_streak(EXTRA_BENEFITS_FILE)
    eb_ext = has_extended_early_bird(EXTRA_BENEFITS_FILE)
    eb_str = "Yes — until 09:00" if eb_ext else "No"

    # Heat skips this month
    this_month = datetime.now(tz=timezone.utc).astimezone().date().strftime("%Y-%m")
    heat_entries = [
        (d, entry)
        for d, entries in log_data.items()
        if d.startswith(this_month)
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("workout_data", {}).get("type") == "heat_skip"
    ]
    if heat_entries:
        last_date, last_e = max(heat_entries, key=lambda de: de[0])
        last_temp = last_e.get("workout_data", {}).get("temperature_celsius", "?")
        heat_str = f"{len(heat_entries)} (last: {last_date}, {last_temp}°C)"
    else:
        heat_str = "0"

    print(f"  Shutdown bonus (this wk): {bonus_hours}h")
    print(f"  Streak (5+ wks)     : {streak}")
    print(f"  Early-bird extended : {eb_str}")
    print(f"  Heat skips (month)  : {heat_str}")
    print()

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

    # Shutdown config
    cfg = locker._read_shutdown_config()
    if cfg:
        _mw, _ts, _morning = cfg
        print(f"  Shutdown tonight    : {_mw:02d}:00")

    sys.exit(0)
