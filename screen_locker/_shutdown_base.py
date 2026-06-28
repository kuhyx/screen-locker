"""Daily shutdown-time base reset for the screen locker.

On each new calendar day the shutdown config is reset to base hours (21:00
by default) so that the day's workout bonuses always layer on top of a known
floor rather than accumulating indefinitely across days.

The sick-day state file is cleared on reset so the sick-restore path cannot
overwrite the fresh base when it runs later in the same startup.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_DEFAULT_BASE_HOUR = 21


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
    except (OSError, json.JSONDecodeError, ValueError):
        return (_DEFAULT_BASE_HOUR, _DEFAULT_BASE_HOUR)


def reset_to_base_if_new_day(
    state_file: Path,
    mixin: object,
    sick_day_state_file: Path | None = None,
) -> bool:
    """Reset the shutdown config to base hours if a new calendar day has begun.

    Writes base hours via *mixin*._write_shutdown_config (with restore=True so
    the script allows moving the time earlier), updates ``last_reset_date`` in
    *state_file*, and removes *sick_day_state_file* if it exists so the
    sick-restore path does not fight with the fresh base on the same startup.

    Returns True if a reset was performed, False if today was already reset.
    """
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    if state_file.exists():
        try:
            with state_file.open() as f:
                state: dict[str, Any] = json.load(f)
            if state.get("last_reset_date") == today:
                return False
        except (OSError, json.JSONDecodeError):
            pass

    base_mw, base_ts = get_base_hours(state_file)

    # Preserve the morning-end hour from the live config.
    config = mixin._read_shutdown_config()
    morning_end = config[2] if config else 5

    ok: bool = mixin._write_shutdown_config(base_mw, base_ts, morning_end, restore=True)
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

    _logger.info("Daily base reset: Mon-Wed=%d, Thu-Sun=%d.", base_mw, base_ts)
    return True
