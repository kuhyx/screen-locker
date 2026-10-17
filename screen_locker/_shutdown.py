"""Shutdown schedule adjustment mixin for the screen locker."""

from __future__ import annotations

from datetime import date
import logging
import subprocess
from typing import TYPE_CHECKING

import earned_time

from screen_locker._constants import (
    ADJUST_SHUTDOWN_SCRIPT,
    SHUTDOWN_CONFIG_FILE,
)
from screen_locker._day import today_str
from screen_locker._earned import ceiling, first_minutes, hhmm, span
from screen_locker._grace_floor import plan_absorb, save_lift
from screen_locker._late_credit import LateCreditMixin
from screen_locker._sick import is_sick
from screen_locker._sick_floor import SickFloorMixin

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# Every time below is minutes after midnight. The config's *_MINUTES keys are
# authoritative; a file written before the minutes migration has only the
# whole-hour *_HOUR keys, read as HOUR * 60.
_SHUTDOWN_CONFIG_NAMES = ("MON_WED", "THU_SUN", "MORNING_END")
_MINUTES_PER_HOUR = 60

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


class ShutdownMixin(SickFloorMixin, LateCreditMixin):
    """Mixin providing shutdown schedule adjustment functionality."""

    def _adjust_shutdown_time_later(self, at: float | None = None) -> bool:
        """Push shutdown later by the first workout's reward, capped at the ceiling.

        ``at`` is when the workout ended (default now): a late one counts from
        it (:mod:`._late_credit`). Returns True if successful, False otherwise.
        """
        day = date.fromisoformat(today_str())
        reward = first_minutes(earned_time.WORKOUT, day)
        if is_sick(day):
            return self._raise_on_sick_day(reward, at)
        late = self._late_write(reward, at)
        if late is not None:
            return late
        bonus, lift = plan_absorb(reward)
        try:
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False
            mon_wed, thu_sun, morning_end = config_values
            ok = self._write_shutdown_config(
                min(ceiling(day), mon_wed + bonus),
                min(ceiling(day), thu_sun + bonus),
                morning_end,
                restore=True,
            )
        except (OSError, ValueError) as e:
            _logger.warning("Failed to adjust shutdown time for workout: %s", e)
            return False
        if ok:
            save_lift(lift)
        return ok

    def _adjust_shutdown_time_by(
        self, extra_minutes: int, at: float | None = None
    ) -> bool:
        """Push shutdown later by *extra_minutes*, capped at 24:00 (midnight).

        Used for earner and extra-workout bonuses. A cap of midnight works
        because ``day-specific-shutdown-check.sh`` fires at 00:00 and catches it
        via the morning-window condition; the helper clamps it to 23:00 anyway.

        ``at`` is when the credit was earned (default now): a late one counts
        from it (:mod:`._late_credit`). Returns True if successful.
        """
        if is_sick(date.fromisoformat(today_str())):
            return self._raise_on_sick_day(extra_minutes, at)
        late = self._late_write(extra_minutes, at)
        if late is not None:
            return late
        # A stale lift recorded before the grace floor went is spent first.
        moved, lift = plan_absorb(extra_minutes)
        try:
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False
            mw, ts, morning = config_values
            ok = self._write_shutdown_config(
                min(_MIDNIGHT, mw + moved),
                min(_MIDNIGHT, ts + moved),
                morning,
                restore=True,
            )
        except (OSError, ValueError) as e:
            _logger.warning(
                "Failed to adjust shutdown time by %s: %s", span(extra_minutes), e
            )
            return False
        if ok:
            save_lift(lift)
        return ok

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
