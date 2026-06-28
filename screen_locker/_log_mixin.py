"""Mixin: workout log persistence (read/write workout_log.json)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from screen_locker._constants import SCHEDULED_SKIPS_FILE

_logger = logging.getLogger(__name__)


class LogMixin:
    """Handles reading and writing workout_log.json for the ScreenLocker."""

    def has_logged_today(self) -> bool:
        """Check if workout has been logged today with valid HMAC."""
        if not self.log_file.exists():  # type: ignore[attr-defined]
            return False
        try:
            with self.log_file.open() as f:  # type: ignore[attr-defined]
                logs = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        else:
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            entry = logs.get(today)
            if entry is None:
                return False
            if verify_entry_hmac(entry):
                return entry.get("workout_data", {}).get("type") != "early_bird"
            if compute_entry_hmac({"_probe": True}) is None and "hmac" not in entry:
                _logger.info("HMAC key unavailable — accepting unsigned entry")
                return entry.get("workout_data", {}).get("type") != "early_bird"
            _logger.warning("HMAC verification failed for today's log entry")
            return False

    def _load_existing_logs(self) -> dict:
        """Load existing workout logs from file."""
        if not self.log_file.exists():  # type: ignore[attr-defined]
            return {}
        try:
            with self.log_file.open() as f:  # type: ignore[attr-defined]
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _is_scheduled_skip_today(self) -> bool:
        """Return True if today's date is listed in the scheduled skips file."""
        if not SCHEDULED_SKIPS_FILE.exists():
            return False
        try:
            with SCHEDULED_SKIPS_FILE.open() as f:
                skips = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        return today in skips

    def save_workout_log(self) -> None:
        """Save workout data to log file with HMAC signature."""
        logs = self._load_existing_logs()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        entry: dict[str, object] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "workout_data": self.workout_data,  # type: ignore[attr-defined]
        }
        signature = compute_entry_hmac(entry)
        if signature is not None:
            entry["hmac"] = signature
        else:
            _logger.warning("HMAC key unavailable — saving unsigned entry")
        logs[today] = entry
        try:
            with self.log_file.open("w") as f:  # type: ignore[attr-defined]
                json.dump(logs, f, indent=2)
        except OSError as e:
            _logger.warning("Could not save workout log: %s", e)
