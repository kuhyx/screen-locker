"""Daily shutdown-time base reset for the screen locker.

On each new calendar day the shutdown config is reset to base hours (21:00
by default) so that the day's workout bonuses always layer on top of a known
floor rather than accumulating indefinitely across days.

The reset re-derives what today's log has ALREADY earned and writes base plus
that in one go. Live credits are read-add-write against the config, so a
workout credited between local midnight and the first locker tick of the day
(a manual log at 00:02, say) had its hours wiped by the reset that followed —
on 2026-09-13 that left the bar at 21:00 with a counted workout on disk.

The sick-day state file is cleared on reset so the sick-restore path cannot
overwrite the fresh base when it runs later in the same startup.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._day import today_str
from screen_locker._log_io import load_workout_log
from screen_locker._weekly_check import count_day_credits
from screen_locker._workout_credit import earned_shutdown_bonus_hours

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_DEFAULT_BASE_HOUR = 21
# Mirrors RESTORE_CEILING in adjust_shutdown_schedule.sh: the script clamps any
# restore above it, so the target is computed against the same ceiling here
# rather than asking for hours the write will silently cut.
_RESTORE_CEILING_HOUR = 23


def today_earned_bonus_hours(log_file: Path, today: str) -> int:
    """Return the shutdown hours today's logged workouts have already earned.

    Counted with the same :func:`~screen_locker._weekly_check.count_day_credits`
    rule as the weekly total, so a workout recorded twice earns once.
    """
    entries = load_workout_log(log_file).get(today, [])
    credit_count = count_day_credits(today, [e for e in entries if isinstance(e, dict)])
    return earned_shutdown_bonus_hours(credit_count)


def get_base_hours(state_file: Path) -> tuple[int, int]:
    """Return ``(base_mon_wed_hour, base_thu_sun_hour)`` from *state_file*.

    Falls back to ``(21, 21)`` if the file is missing or corrupt.
    """
    if not state_file.exists():
        return (_DEFAULT_BASE_HOUR, _DEFAULT_BASE_HOUR)
    try:
        with state_file.open() as f:
            state: dict[str, Any] = json.load(f)
        return (
            int(state.get("base_mon_wed_hour", _DEFAULT_BASE_HOUR)),
            int(state.get("base_thu_sun_hour", _DEFAULT_BASE_HOUR)),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _logger.warning(
            "Could not read shutdown base hours from %s: %s — defaulting both "
            "to %02d:00",
            state_file,
            exc,
            _DEFAULT_BASE_HOUR,
        )
        return (_DEFAULT_BASE_HOUR, _DEFAULT_BASE_HOUR)


def reset_to_base_if_new_day(
    state_file: Path,
    mixin: object,
    sick_day_state_file: Path | None = None,
    log_file: Path | None = None,
) -> bool:
    """Reset the shutdown config to base hours if a new calendar day has begun.

    Writes base hours plus whatever *log_file* shows today has already earned
    (see :func:`today_earned_bonus_hours`) via *mixin*._write_shutdown_config
    (with restore=True so the script allows moving the time earlier), updates
    ``last_reset_date`` in *state_file*, and removes *sick_day_state_file* if
    it exists so the sick-restore path does not fight with the fresh base on
    the same startup.

    Returns True if a reset was performed, False if today was already reset.
    """
    today = today_str()

    if state_file.exists():
        try:
            with state_file.open() as f:
                state: dict[str, Any] = json.load(f)
            if state.get("last_reset_date") == today:
                return False
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning(
                "Could not read last_reset_date from %s: %s — cannot tell if "
                "today was already reset, so resetting to base hours again",
                state_file,
                exc,
            )

    base_mw, base_ts = get_base_hours(state_file)
    earned = today_earned_bonus_hours(log_file, today) if log_file is not None else 0
    target_mw = min(_RESTORE_CEILING_HOUR, base_mw + earned)
    target_ts = min(_RESTORE_CEILING_HOUR, base_ts + earned)

    # Preserve the morning-end hour from the live config.
    config = mixin._read_shutdown_config()
    morning_end = config[2] if config else 5

    ok: bool = mixin._write_shutdown_config(
        target_mw, target_ts, morning_end, restore=True
    )
    if not ok:
        _logger.warning("Daily base reset: failed to write shutdown config.")
        return False

    # Clear stale sick-day state so it does not override the base reset.
    if sick_day_state_file is not None and sick_day_state_file.exists():
        try:
            sick_day_state_file.unlink()
            _logger.info("Daily base reset: cleared stale sick-day state.")
        except OSError as exc:
            _logger.warning(
                "Daily base reset: could not remove sick-day state: %s", exc
            )

    new_state: dict[str, Any] = {
        "base_mon_wed_hour": base_mw,
        "base_thu_sun_hour": base_ts,
        "last_reset_date": today,
    }
    try:
        with state_file.open("w") as f:
            json.dump(new_state, f, indent=2)
    except OSError as exc:
        _logger.warning("Daily base reset: failed to write state file: %s", exc)

    _logger.info(
        "Daily base reset: Mon-Wed=%d, Thu-Sun=%d (base %d/%d + %dh already "
        "earned today).",
        target_mw,
        target_ts,
        base_mw,
        base_ts,
        earned,
    )
    return True
