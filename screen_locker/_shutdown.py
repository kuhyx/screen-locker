"""Shutdown schedule adjustment mixin for the screen locker."""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from screen_locker._constants import (
    ADJUST_SHUTDOWN_SCRIPT,
    SHUTDOWN_CONFIG_FILE,
)
from screen_locker._day import today_str
from screen_locker._earned import hhmm, span
from screen_locker._shutdown_sick_state import SickDayStateMixin
from screen_locker._workout_credit import FIRST_WORKOUT_BONUS_MINUTES

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# Every time below is minutes after midnight. The config's *_MINUTES keys are
# authoritative; a file written before the minutes migration has only the
# whole-hour *_HOUR keys, read as HOUR * 60.
_SHUTDOWN_CONFIG_NAMES = ("MON_WED", "THU_SUN", "MORNING_END")
_MINUTES_PER_HOUR = 60

# A sick day moves shutdown an hour earlier, but never before 18:00.
_SICK_DAY_STEP = 60
_SICK_DAY_FLOOR = 18 * _MINUTES_PER_HOUR
# The workout reward stops at 23:00 (adjust_shutdown_schedule.sh's ceiling).
_WORKOUT_CEILING = 23 * _MINUTES_PER_HOUR
# Extra bonuses may name midnight; the helper still clamps them to 23:00.
_MIDNIGHT = 24 * _MINUTES_PER_HOUR


def _parse_config(path: Path) -> dict[str, int]:
    """Every integer ``KEY=value`` line of *path*."""
    parsed: dict[str, int] = {}
    with path.open() as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and value.strip().isdigit():
                parsed[key] = int(value)
    return parsed


def read_shutdown_config(path: Path) -> tuple[int, int, int] | None:
    """Read shutdown config from *path* as (mon_wed, thu_sun, morning_end) minutes.

    Reading needs no privilege (only writing does, via
    ``adjust_shutdown_schedule.sh``) — safe to call from a read-only status view.
    """
    if not path.exists():
        _logger.warning("Config not found: %s", path)
        return None
    parsed = _parse_config(path)
    values: list[int] = []
    for name in _SHUTDOWN_CONFIG_NAMES:
        if f"{name}_MINUTES" in parsed:
            values.append(parsed[f"{name}_MINUTES"])
        elif f"{name}_HOUR" in parsed:
            values.append(parsed[f"{name}_HOUR"] * _MINUTES_PER_HOUR)
        else:
            _logger.warning("Shutdown config missing required values")
            return None
    mon_wed, thu_sun, morning_end = values
    return mon_wed, thu_sun, morning_end


class ShutdownMixin(SickDayStateMixin):
    """Mixin providing shutdown schedule adjustment functionality."""

    def _apply_earlier_shutdown(self, today: str) -> bool:
        """Read config, save state, and write an earlier shutdown time."""
        config_values = self._read_shutdown_config()
        if config_values is None:
            return False
        mon_wed, thu_sun, morning_end = config_values
        if not self._save_sick_day_state(today, mon_wed, thu_sun):
            _logger.error("Failed to save state - aborting adjustment")
            return False
        return self._write_shutdown_config(
            max(_SICK_DAY_FLOOR, mon_wed - _SICK_DAY_STEP),
            max(_SICK_DAY_FLOOR, thu_sun - _SICK_DAY_STEP),
            morning_end,
        )

    def _adjust_shutdown_time_earlier(self) -> bool:
        """Adjust shutdown schedule an hour earlier (stricter).

        This can only be used once per day. Original values are saved and
        automatically restored when checked the next day.

        Returns True if successful, False otherwise.
        """
        today = today_str()
        self._restore_original_config_if_needed()
        if self._sick_mode_used_today():
            _logger.warning("Sick mode already used today")
            return False
        try:
            return self._apply_earlier_shutdown(today)
        except (OSError, ValueError) as e:
            _logger.warning("Failed to adjust shutdown time: %s", e)
            return False

    def _adjust_shutdown_time_later(self) -> bool:
        """Push shutdown later by the first workout's reward, capped at 23:00.

        Returns True if successful, False otherwise.
        """
        try:
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False
            mon_wed, thu_sun, morning_end = config_values
            return self._write_shutdown_config(
                min(_WORKOUT_CEILING, mon_wed + FIRST_WORKOUT_BONUS_MINUTES),
                min(_WORKOUT_CEILING, thu_sun + FIRST_WORKOUT_BONUS_MINUTES),
                morning_end,
                restore=True,
            )
        except (OSError, ValueError) as e:
            _logger.warning("Failed to adjust shutdown time for workout: %s", e)
            return False

    def _adjust_shutdown_time_by(self, extra_minutes: int) -> bool:
        """Push shutdown later by *extra_minutes*, capped at 24:00 (midnight).

        Used for earner and extra-workout bonuses. A cap of midnight works
        because ``day-specific-shutdown-check.sh`` fires at 00:00 and catches it
        via the morning-window condition; the helper clamps it to 23:00 anyway.

        Returns True if successful, False otherwise.
        """
        try:
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False
            mw, ts, morning = config_values
            return self._write_shutdown_config(
                min(_MIDNIGHT, mw + extra_minutes),
                min(_MIDNIGHT, ts + extra_minutes),
                morning,
                restore=True,
            )
        except (OSError, ValueError) as e:
            _logger.warning(
                "Failed to adjust shutdown time by %s: %s", span(extra_minutes), e
            )
            return False

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        """Read shutdown config as (mon_wed, thu_sun, morning_end) minutes, or None."""
        return read_shutdown_config(SHUTDOWN_CONFIG_FILE)

    def _build_shutdown_cmd(
        self,
        mon_wed: int,
        thu_sun: int,
        morning: int,
        *,
        restore: bool,
    ) -> list[str]:
        """Build the shutdown adjustment command."""
        cmd = ["/usr/bin/sudo", str(ADJUST_SHUTDOWN_SCRIPT)]
        if restore:
            cmd.append("--restore")
        cmd.extend([hhmm(mon_wed), hhmm(thu_sun), hhmm(morning)])
        return cmd

    def _write_shutdown_config(
        self,
        mon_wed: int,
        thu_sun: int,
        morning_end: int,
        *,
        restore: bool = False,
    ) -> bool:
        """Write new shutdown config values using helper script.

        Args:
            mon_wed: Monday-Wednesday shutdown, minutes after midnight.
            thu_sun: Thursday-Sunday shutdown, minutes after midnight.
            morning_end: End of the morning window, minutes after midnight.
            restore: If True, allows restoring to later times.

        Returns True if successful, False otherwise.
        """
        if not ADJUST_SHUTDOWN_SCRIPT.exists():
            _logger.warning(
                "Script not found: %s",
                ADJUST_SHUTDOWN_SCRIPT,
            )
            return False
        cmd = self._build_shutdown_cmd(
            mon_wed,
            thu_sun,
            morning_end,
            restore=restore,
        )
        return self._run_shutdown_cmd(cmd, mon_wed, thu_sun)

    def _run_shutdown_cmd(
        self,
        cmd: list[str],
        mon_wed: int,
        thu_sun: int,
    ) -> bool:
        """Execute the shutdown adjustment command."""
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.SubprocessError as e:
            _logger.warning("Failed to adjust shutdown config: %s", e)
            return False
        _logger.info(
            "Adjusted shutdown: Mon-Wed=%s, Thu-Sun=%s. %s",
            hhmm(mon_wed),
            hhmm(thu_sun),
            result.stdout.strip(),
        )
        return True
