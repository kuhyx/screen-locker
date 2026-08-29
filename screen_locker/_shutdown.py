"""Shutdown schedule adjustment mixin for the screen locker."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import subprocess
from typing import TYPE_CHECKING

from screen_locker._constants import (
    ADJUST_SHUTDOWN_SCRIPT,
    SHUTDOWN_CONFIG_FILE,
)
from screen_locker._shutdown_sick_state import SickDayStateMixin
from screen_locker._wake_alarm import WakeAlarmMixin

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_SHUTDOWN_CONFIG_KEYS = ("MON_WED_HOUR", "THU_SUN_HOUR", "MORNING_END_HOUR")


def read_shutdown_config(path: Path) -> tuple[int, int, int] | None:
    """Read shutdown config from *path*. Returns (mw_hour, ts_hour, me_hour) or None.

    Reading needs no privilege (only writing does, via
    ``adjust_shutdown_schedule.sh``) — safe to call from a read-only status view.
    """
    if not path.exists():
        _logger.warning("Config not found: %s", path)
        return None
    parsed: dict[str, int] = {}
    with path.open() as f:
        for line in f:
            stripped = line.strip()
            for key in _SHUTDOWN_CONFIG_KEYS:
                if stripped.startswith(f"{key}="):
                    parsed[key] = int(stripped.split("=")[1])
    if len(parsed) < len(_SHUTDOWN_CONFIG_KEYS):
        _logger.warning("Shutdown config missing required values")
        return None
    return (
        parsed["MON_WED_HOUR"],
        parsed["THU_SUN_HOUR"],
        parsed["MORNING_END_HOUR"],
    )


class ShutdownMixin(SickDayStateMixin, WakeAlarmMixin):
    """Mixin providing shutdown schedule adjustment functionality."""

    def _apply_earlier_shutdown(self, today: str) -> bool:
        """Read config, save state, and write earlier shutdown hours."""
        config_values = self._read_shutdown_config()
        if config_values is None:
            return False
        mon_wed_hour, thu_sun_hour, morning_end_hour = config_values
        if not self._save_sick_day_state(today, mon_wed_hour, thu_sun_hour):
            _logger.error("Failed to save state - aborting adjustment")
            return False
        new_mon_wed = max(18, mon_wed_hour - 1)
        new_thu_sun = max(18, thu_sun_hour - 1)
        return self._write_shutdown_config(
            new_mon_wed,
            new_thu_sun,
            morning_end_hour,
        )

    def _adjust_shutdown_time_earlier(self) -> bool:
        """Adjust shutdown schedule 1.5 hours earlier (stricter).

        This can only be used once per day. Original values are saved and
        automatically restored when checked the next day.

        Returns True if successful, False otherwise.
        """
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
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
        """Adjust shutdown schedule 2 hours later as workout reward.

        Returns True if successful, False otherwise.
        """
        try:
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False
            mon_wed_hour, thu_sun_hour, morning_end_hour = config_values
            new_mon_wed = min(23, mon_wed_hour + 2)
            new_thu_sun = min(23, thu_sun_hour + 2)
            return self._write_shutdown_config(
                new_mon_wed,
                new_thu_sun,
                morning_end_hour,
                restore=True,
            )
        except (OSError, ValueError) as e:
            _logger.warning("Failed to adjust shutdown time for workout: %s", e)
            return False

    def _adjust_shutdown_time_by(self, extra_hours: int) -> bool:
        """Adjust shutdown hours by *extra_hours*, capped at 24 (midnight).

        Used for extra-workout bonuses beyond the weekly minimum.  A cap of 24
        works because ``day-specific-shutdown-check.sh`` fires at 00:00 and
        catches it via the morning-window condition (0 <= 300 minutes).

        Returns True if successful, False otherwise.
        """
        try:
            config_values = self._read_shutdown_config()
            if config_values is None:
                return False
            mw, ts, morning = config_values
            return self._write_shutdown_config(
                min(24, mw + extra_hours),
                min(24, ts + extra_hours),
                morning,
                restore=True,
            )
        except (OSError, ValueError) as e:
            _logger.warning(
                "Failed to adjust shutdown time by %d h: %s", extra_hours, e
            )
            return False

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        """Read shutdown config. Returns (mw_hour, ts_hour, me_hour) or None."""
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
        cmd.extend([str(mon_wed), str(thu_sun), str(morning)])
        return cmd

    def _write_shutdown_config(
        self,
        mon_wed_hour: int,
        thu_sun_hour: int,
        morning_end_hour: int,
        *,
        restore: bool = False,
    ) -> bool:
        """Write new shutdown config values using helper script.

        Args:
            mon_wed_hour: Shutdown hour for Monday-Wednesday.
            thu_sun_hour: Shutdown hour for Thursday-Sunday.
            morning_end_hour: Morning end hour.
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
            mon_wed_hour,
            thu_sun_hour,
            morning_end_hour,
            restore=restore,
        )
        return self._run_shutdown_cmd(cmd, mon_wed_hour, thu_sun_hour)

    def _run_shutdown_cmd(
        self,
        cmd: list[str],
        mon_wed_hour: int,
        thu_sun_hour: int,
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
            "Adjusted shutdown: Mon-Wed=%d, Thu-Sun=%d. %s",
            mon_wed_hour,
            thu_sun_hour,
            result.stdout.strip(),
        )
        return True
