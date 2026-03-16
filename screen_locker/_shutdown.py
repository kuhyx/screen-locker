"""Shutdown schedule adjustment mixin for the screen locker."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import subprocess

from python_pkg.screen_locker._constants import (
    ADJUST_SHUTDOWN_SCRIPT,
    SHUTDOWN_CONFIG_FILE,
    SICK_DAY_STATE_FILE,
)

_logger = logging.getLogger(__name__)


class ShutdownMixin:
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
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
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

    def _sick_mode_used_today(self) -> bool:
        """Check if sick mode was already used today."""
        if not SICK_DAY_STATE_FILE.exists():
            return False

        try:
            with SICK_DAY_STATE_FILE.open() as f:
                state = json.load(f)
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            return state.get("date") == today
        except (OSError, json.JSONDecodeError):
            return False

    def _save_sick_day_state(
        self,
        date: str,
        orig_mon_wed: int,
        orig_thu_sun: int,
    ) -> bool:
        """Save sick day state with original config values.

        Returns True if saved successfully, False otherwise.
        """
        state = {
            "date": date,
            "original_mon_wed_hour": orig_mon_wed,
            "original_thu_sun_hour": orig_thu_sun,
        }
        try:
            with SICK_DAY_STATE_FILE.open("w") as f:
                json.dump(state, f, indent=2)
        except OSError as e:
            _logger.warning("Failed to save sick day state: %s", e)
            return False

        _logger.info("Saved sick day state for %s", date)
        return True

    def _load_sick_day_state(self) -> tuple[str, int, int] | None:
        """Load sick day state file.

        Returns (date, orig_mon_wed_hour, orig_thu_sun_hour) or None.
        """
        with SICK_DAY_STATE_FILE.open() as f:
            state = json.load(f)
        date = state.get("date")
        orig_mw = state.get("original_mon_wed_hour")
        orig_ts = state.get("original_thu_sun_hour")
        if date is None or orig_mw is None or orig_ts is None:
            return None
        return (str(date), int(orig_mw), int(orig_ts))

    def _write_restored_config(
        self,
        orig_mw: int,
        orig_ts: int,
        state_date: str,
    ) -> None:
        """Write restored config values and clean up state file."""
        config_values = self._read_shutdown_config()
        if config_values:
            _, _, morning_end = config_values
            _logger.info(
                "Restoring original shutdown config from %s",
                state_date,
            )
            self._write_shutdown_config(
                orig_mw,
                orig_ts,
                morning_end,
                restore=True,
            )
        SICK_DAY_STATE_FILE.unlink()
        _logger.info("Removed stale sick day state from %s", state_date)

    def _restore_original_config_if_needed(self) -> None:
        """Restore original config if sick day state is from a previous day."""
        if not SICK_DAY_STATE_FILE.exists():
            return
        try:
            loaded = self._load_sick_day_state()
            if loaded is None:
                return
            state_date, orig_mw, orig_ts = loaded
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            if state_date != today:
                self._write_restored_config(orig_mw, orig_ts, state_date)
        except (OSError, json.JSONDecodeError) as e:
            _logger.warning("Error checking sick day state: %s", e)

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        """Read shutdown config. Returns (mw_hour, ts_hour, me_hour) or None."""
        if not SHUTDOWN_CONFIG_FILE.exists():
            _logger.warning("Config not found: %s", SHUTDOWN_CONFIG_FILE)
            return None
        parsed: dict[str, int] = {}
        keys = ("MON_WED_HOUR", "THU_SUN_HOUR", "MORNING_END_HOUR")
        with SHUTDOWN_CONFIG_FILE.open() as f:
            for line in f:
                stripped = line.strip()
                for key in keys:
                    if stripped.startswith(f"{key}="):
                        parsed[key] = int(stripped.split("=")[1])
        if len(parsed) < len(keys):
            _logger.warning("Shutdown config missing required values")
            return None
        return (
            parsed["MON_WED_HOUR"],
            parsed["THU_SUN_HOUR"],
            parsed["MORNING_END_HOUR"],
        )

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
