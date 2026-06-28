"""Non-locking status view: workout count, bonuses, RunnerUp scan trigger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sys
from typing import TYPE_CHECKING

from screen_locker._constants import EXTRA_BENEFITS_FILE
from screen_locker._extra_benefits import (
    current_streak,
    has_extended_early_bird,
)
from screen_locker._weekly_check import (
    COUNTED_WORKOUT_TYPES,
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
)

if TYPE_CHECKING:
    from pathlib import Path

    from screen_locker.screen_lock import ScreenLocker


def _load_log(log_file: Path) -> dict:
    """Load the workout log dict, returning {} on any error."""
    if not log_file.exists():
        return {}
    try:
        with log_file.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _load_extra_benefits() -> dict:
    """Load extra_benefits_state.json, returning {} on any error."""
    if not EXTRA_BENEFITS_FILE.exists():
        return {}
    try:
        return json.loads(EXTRA_BENEFITS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def run_status(locker: ScreenLocker) -> None:
    """Print weekly workout status, run RunnerUp scan, apply bonus, then exit."""
    today = datetime.now(tz=timezone.utc).astimezone().date()
    monday = today - timedelta(days=today.weekday())
    log_file: Path = locker.log_file  # type: ignore[attr-defined]
    log_data = _load_log(log_file)

    print("=== Weekly Workout Status ===")

    # Per-day breakdown
    before_count = 0
    for i in range(7):
        d = monday + timedelta(days=i)
        if d > today:
            break
        dstr = d.isoformat()
        entry = log_data.get(dstr)
        if entry is None:
            print(f"  {d.strftime('%a %b %d')}  —  no entry")
        else:
            wtype = entry.get("workout_data", {}).get("type", "?")
            src = entry.get("workout_data", {}).get("source", "")
            counted = wtype in COUNTED_WORKOUT_TYPES
            src_str = f"  ({src[:45]})" if src else ""
            mark = "✓" if counted else "✗"
            print(f"  {d.strftime('%a %b %d')}  {mark}  {wtype}{src_str}")
            if counted:
                before_count += 1

    print()

    # RunnerUp scan
    n_filled = locker._scan_and_fill_week_runnerup(log_file)  # type: ignore[attr-defined]
    if n_filled > 0:
        print(f"  Auto-filled {n_filled} workout(s) from RunnerUp exports.")
        after_count = count_weekly_workouts(log_file)
        bonus = max(0, after_count - max(WEEKLY_WORKOUT_MINIMUM, before_count))
        if bonus > 0:
            ok = locker._adjust_shutdown_time_by(bonus)  # type: ignore[attr-defined]
            if ok:
                print(f"  +{bonus}h shutdown bonus applied.")
            else:
                print(f"  +{bonus}h shutdown bonus pending (config write failed).")
    else:
        print("  No new workouts found via RunnerUp scan.")
        after_count = before_count

    print()

    # Extra benefits summary
    state = _load_extra_benefits()
    credits = state.get("skip_credits", 0)
    streak = current_streak(EXTRA_BENEFITS_FILE)
    eb_ext = has_extended_early_bird(EXTRA_BENEFITS_FILE)
    eb_str = "Yes — until 09:00" if eb_ext else "No"

    print(f"  Skip credits banked : {credits}")
    print(f"  Streak (5+ wks)     : {streak}")
    print(f"  Early-bird extended : {eb_str}")
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
    cfg = locker._read_shutdown_config()  # type: ignore[attr-defined]
    if cfg:
        _mw, _ts, _morning = cfg
        print(f"  Shutdown tonight    : {_mw:02d}:00")

    sys.exit(0)
