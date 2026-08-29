"""Sick-day shutdown state: persistence and next-day restoration.

Split out of :mod:`screen_locker._shutdown` to keep every file under the
250-line cap. Composed back into ``ShutdownMixin`` there, so callers see no
change.

Tracks the shutdown hours that were in force before a sick day moved them
earlier, so the following day can put them back.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging

from screen_locker._constants import SICK_DAY_STATE_FILE

_logger = logging.getLogger(__name__)


class SickDayStateMixin:
    """Persists and restores the pre-sick-day shutdown configuration."""

    def _sick_mode_used_today(self) -> bool:
        """Check if sick mode was already used today."""
        if not SICK_DAY_STATE_FILE.exists():
            return False

        try:
            with SICK_DAY_STATE_FILE.open() as f:
                state = json.load(f)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            return state.get("date") == today
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning(
                "Could not read sick-day state from %s: %s — treating sick mode "
                "as UNUSED today, which may allow a second sick day",
                SICK_DAY_STATE_FILE,
                exc,
            )
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
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            if state_date != today:
                self._write_restored_config(orig_mw, orig_ts, state_date)
        except (OSError, json.JSONDecodeError) as e:
            _logger.warning("Error checking sick day state: %s", e)
