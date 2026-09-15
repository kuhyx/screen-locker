"""Daily shutdown-time base reset for the screen locker.

On each new calendar day the shutdown config is reset to the base hour
(:data:`BASE_HOUR`, 20:00) so that the day's bonuses always layer on top of a
known floor rather than accumulating indefinitely across days.

The base is a constant, not state. It used to be persisted in the state file
and read back on every reset, which made the code's default dead: the file
kept re-writing whatever it was installed with, so changing the constant
changed nothing on the machine. The state file now carries only date stamps.

The reset re-derives what today has ALREADY earned and writes base plus that
in one go: the workout hours from today's log, and the LeetCode hour from
leetcode-guard's ledger (:mod:`screen_locker._leetcode_bonus`). Live credits
are read-add-write against the config, so a workout credited between local
midnight and the first locker tick of the day (a manual log at 00:02, say)
had its hours wiped by the reset that followed -- on 2026-09-13 that left the
bar at 21:00 with a counted workout on disk. Any bonus source that is not a
term of this derivation has that bug.

The sick-day state file is cleared on reset so the sick-restore path cannot
overwrite the fresh base when it runs later in the same startup.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._day import today_str
from screen_locker._leetcode_bonus import LEETCODE_BONUS_HOURS, leetcode_bonus_hours
from screen_locker._log_io import load_workout_log
from screen_locker._weekly_check import count_day_credits
from screen_locker._workout_credit import earned_shutdown_bonus_hours

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# The hour every day starts from before any bonus. Moved 21 -> 20 on 2026-09-15.
BASE_HOUR = 20
# Mirrors RESTORE_CEILING in adjust_shutdown_schedule.sh: the script clamps any
# restore above it, so the target is computed against the same ceiling here
# rather than asking for hours the write will silently cut.
_RESTORE_CEILING_HOUR = 23

_LEETCODE_STAMP = "leetcode_bonus_date"


def today_earned_bonus_hours(log_file: Path, today: str) -> int:
    """Return the shutdown hours today's logged workouts have already earned.

    Counted with the same :func:`~screen_locker._weekly_check.count_day_credits`
    rule as the weekly total, so a workout recorded twice earns once.
    """
    entries = load_workout_log(log_file).get(today, [])
    credit_count = count_day_credits(today, [e for e in entries if isinstance(e, dict)])
    return earned_shutdown_bonus_hours(credit_count)


def _load_state(state_file: Path) -> dict[str, Any]:
    """Return the reset state, or an empty dict when it is missing or corrupt.

    A corrupt file is logged and treated as "nothing stamped": the reset then
    runs again, which is idempotent, and the LeetCode hour is re-applied at
    worst once, capped by the ceiling.
    """
    if not state_file.exists():
        return {}
    try:
        with state_file.open() as f:
            state: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "Could not read shutdown reset state from %s: %s -- treating today "
            "as not yet reset",
            state_file,
            exc,
        )
        return {}
    return state


def _save_state(state_file: Path, state: dict[str, Any]) -> None:
    """Write the reset state, logging rather than raising on failure."""
    try:
        with state_file.open("w") as f:
            json.dump(state, f, indent=2)
    except OSError as exc:
        _logger.warning("Failed to write shutdown reset state: %s", exc)


def _clear_sick_day_state(sick_day_state_file: Path | None) -> None:
    """Remove stale sick-day state so it does not override the base reset."""
    if sick_day_state_file is None or not sick_day_state_file.exists():
        return
    try:
        sick_day_state_file.unlink()
        _logger.info("Daily base reset: cleared stale sick-day state.")
    except OSError as exc:
        _logger.warning("Daily base reset: could not remove sick-day state: %s", exc)


def reset_to_base_if_new_day(
    state_file: Path,
    mixin: object,
    sick_day_state_file: Path | None = None,
    log_file: Path | None = None,
) -> bool:
    """Reset the shutdown config to the base hour if a new calendar day began.

    Writes :data:`BASE_HOUR` plus whatever today has already earned -- the
    workout hours in *log_file* (see :func:`today_earned_bonus_hours`) and the
    LeetCode hour -- via *mixin*._write_shutdown_config (with restore=True so
    the script allows moving the time earlier), stamps ``last_reset_date`` in
    *state_file*, and removes *sick_day_state_file* if it exists so the
    sick-restore path does not fight with the fresh base on the same startup.

    Returns True if a reset was performed, False if today was already reset.
    """
    today = today_str()
    if _load_state(state_file).get("last_reset_date") == today:
        return False

    earned = today_earned_bonus_hours(log_file, today) if log_file is not None else 0
    leetcode = leetcode_bonus_hours()
    target = min(_RESTORE_CEILING_HOUR, BASE_HOUR + earned + leetcode)

    # Preserve the morning-end hour from the live config.
    config = mixin._read_shutdown_config()
    morning_end = config[2] if config else 5

    ok: bool = mixin._write_shutdown_config(target, target, morning_end, restore=True)
    if not ok:
        _logger.warning("Daily base reset: failed to write shutdown config.")
        return False

    _clear_sick_day_state(sick_day_state_file)

    # The LeetCode hour is stamped here too: the reset already included it, so
    # the live pass below must not add it a second time today.
    new_state: dict[str, Any] = {"last_reset_date": today}
    if leetcode:
        new_state[_LEETCODE_STAMP] = today
    _save_state(state_file, new_state)

    _logger.info(
        "Daily base reset: %02d:00 (base %d + %dh workout + %dh LeetCode "
        "already earned today).",
        target,
        BASE_HOUR,
        earned,
        leetcode,
    )
    return True


def apply_leetcode_bonus_if_new(state_file: Path, mixin: object) -> bool:
    """Push shutdown later by the LeetCode hour, once per day, if it is earned.

    The daily reset only sees a solve that happened before it ran; this is
    the live counterpart for the usual case, where the solve lands hours
    later and is picked up by the next timer tick. Idempotent through the
    ``leetcode_bonus_date`` stamp in *state_file*, which the reset sets as
    well when it already included the hour.

    Returns True if the hour was applied on this call.
    """
    today = today_str()
    state = _load_state(state_file)
    if state.get(_LEETCODE_STAMP) == today or leetcode_bonus_hours() == 0:
        return False
    if not mixin._adjust_shutdown_time_by(LEETCODE_BONUS_HOURS):
        _logger.warning("LeetCode bonus: failed to write shutdown config.")
        return False
    state[_LEETCODE_STAMP] = today
    _save_state(state_file, state)
    _logger.info("LeetCode bonus: +%dh shutdown time today.", LEETCODE_BONUS_HOURS)
    return True
