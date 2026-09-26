"""Daily shutdown-time base reset for the screen locker.

On each new calendar day the shutdown config is reset to the base hour
(:data:`BASE_HOUR`, 19:00) so that the day's bonuses always layer on top of a
known floor rather than accumulating indefinitely across days.

The base is a constant, not state. It used to be persisted in the state file
and read back on every reset, which made the code's default dead: the file
kept re-writing whatever it was installed with, so changing the constant
changed nothing on the machine. The state file now carries only date stamps.

The reset re-derives what today has ALREADY earned and writes base plus that
in one go: the workout hours from today's log, the LeetCode hour from
leetcode-guard's ledger (:mod:`screen_locker._leetcode_bonus`) and the reading
hour from book-guard's (:mod:`screen_locker._reading_bonus`). Live credits
are read-add-write against the config, so a workout credited between local
midnight and the first locker tick of the day (a manual log at 00:02, say)
had its hours wiped by the reset that followed -- on 2026-09-13 that left the
bar at 21:00 with a counted workout on disk. Any bonus source that is not a
term of this derivation has that bug.

The sick-day state file is cleared on reset so the sick-restore path cannot
overwrite the fresh base when it runs later in the same startup.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._day import today_str
from screen_locker._leetcode_bonus import LEETCODE_BONUS_HOURS, leetcode_bonus_hours
from screen_locker._log_io import load_workout_log
from screen_locker._reading_bonus import READING_BONUS_HOURS, reading_bonus_hours
from screen_locker._weekly_check import count_day_credits
from screen_locker._workout_credit import earned_shutdown_bonus_hours

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_logger = logging.getLogger(__name__)

# The hour every day starts from before any bonus. Moved 21 -> 20 on
# 2026-09-15, and 20 -> 19 together with book-guard's reading hour: the
# ceiling stays 23:00, so every day's best case (workouts + LeetCode + reading)
# is unchanged and a day without reading ends an hour earlier. The cut waits
# for book-guard's gate (2026-10-01) -- taking an hour the reader cannot yet
# earn back was a same-day loss when it first shipped on 2026-09-26.
BASE_HOUR = 19
READING_BASE_FROM = date(2026, 10, 1)


def base_hour(day: date | None = None) -> int:
    """The base for ``day`` (default today): 20 before the reading cut, then 19."""
    target = day or datetime.now().astimezone().date()
    return BASE_HOUR if target >= READING_BASE_FROM else BASE_HOUR + 1


# Mirrors RESTORE_CEILING in adjust_shutdown_schedule.sh: the script clamps any
# restore above it, so the target is computed against the same ceiling here
# rather than asking for hours the write will silently cut.
_RESTORE_CEILING_HOUR = 23

_LEETCODE_STAMP = "leetcode_bonus_date"
_READING_STAMP = "reading_bonus_date"


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
    reading = reading_bonus_hours()
    base = base_hour()
    target = min(_RESTORE_CEILING_HOUR, base + earned + leetcode + reading)

    # Preserve the morning-end hour from the live config.
    config = mixin._read_shutdown_config()
    morning_end = config[2] if config else 5

    ok: bool = mixin._write_shutdown_config(target, target, morning_end, restore=True)
    if not ok:
        _logger.warning("Daily base reset: failed to write shutdown config.")
        return False

    _clear_sick_day_state(sick_day_state_file)

    # The flat hours are stamped here too: the reset already included them,
    # so the live pass below must not add them a second time today.
    new_state: dict[str, Any] = {"last_reset_date": today}
    if leetcode:
        new_state[_LEETCODE_STAMP] = today
    if reading:
        new_state[_READING_STAMP] = today
    _save_state(state_file, new_state)

    _logger.info(
        "Daily base reset: %02d:00 (base %d + %dh workout + %dh LeetCode + "
        "%dh reading already earned today).",
        target,
        base,
        earned,
        leetcode,
        reading,
    )
    return True


def _apply_flat_bonus(
    state_file: Path,
    mixin: object,
    *,
    stamp: str,
    hours: Callable[[], int],
    label: str,
) -> bool:
    """Push shutdown later by a once-per-day flat hour, if it is earned.

    The daily reset only sees a bonus earned before it ran; this is the live
    counterpart for the usual case, where the solve or the reading lands
    hours later and is picked up by the next timer tick. Idempotent through
    the ``stamp`` key in *state_file*, which the reset sets as well when it
    already included the hour.

    Returns True if the hour was applied on this call.
    """
    today = today_str()
    state = _load_state(state_file)
    if state.get(stamp) == today:
        return False
    earned = hours()
    if earned == 0:
        return False
    if not mixin._adjust_shutdown_time_by(earned):
        _logger.warning("%s bonus: failed to write shutdown config.", label)
        return False
    state[stamp] = today
    _save_state(state_file, state)
    _logger.info("%s bonus: +%dh shutdown time today.", label, earned)
    return True


def apply_leetcode_bonus_if_new(state_file: Path, mixin: object) -> bool:
    """The LeetCode hour, live (see :func:`_apply_flat_bonus`)."""
    return _apply_flat_bonus(
        state_file,
        mixin,
        stamp=_LEETCODE_STAMP,
        hours=lambda: LEETCODE_BONUS_HOURS if leetcode_bonus_hours() else 0,
        label="LeetCode",
    )


def apply_reading_bonus_if_new(state_file: Path, mixin: object) -> bool:
    """The reading hour, live (see :func:`_apply_flat_bonus`)."""
    return _apply_flat_bonus(
        state_file,
        mixin,
        stamp=_READING_STAMP,
        hours=lambda: READING_BONUS_HOURS if reading_bonus_hours() else 0,
        label="Reading",
    )


def apply_flat_bonuses_if_new(state_file: Path, mixin: object) -> None:
    """Every once-per-day flat hour: LeetCode, then reading."""
    apply_leetcode_bonus_if_new(state_file, mixin)
    apply_reading_bonus_if_new(state_file, mixin)
