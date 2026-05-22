"""Early bird window detection and log helpers for ScreenLocker."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from python_pkg.screen_locker._constants import (
    EARLY_BIRD_END_HOUR,
    EARLY_BIRD_END_MINUTE,
    EARLY_BIRD_START_HOUR,
)

_logger = logging.getLogger(__name__)


class EarlyBirdMixin:
    """Mixin providing early-bird time window checks and log helpers."""

    def _get_local_time_minutes(self) -> int:
        """Return current local time as minutes from midnight."""
        now = datetime.now(tz=timezone.utc).astimezone()
        return now.hour * 60 + now.minute

    def _is_early_bird_time(self) -> bool:
        """Return True if current local time is in the early bird window."""
        minutes = self._get_local_time_minutes()
        start = EARLY_BIRD_START_HOUR * 60
        end = EARLY_BIRD_END_HOUR * 60 + EARLY_BIRD_END_MINUTE
        return start <= minutes < end

    def _is_early_bird_log(self) -> bool:
        """Check if today's workout log entry is an early_bird provisional entry."""
        if not self.log_file.exists():
            return False
        try:
            with self.log_file.open() as f:
                logs = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        entry = logs.get(today)
        if entry is None:
            return False
        return entry.get("workout_data", {}).get("type") == "early_bird"

    def _save_early_bird_log(self) -> None:
        """Save an early_bird provisional entry to the workout log."""
        self.workout_data = {"type": "early_bird"}
        self.save_workout_log()

    def _try_auto_upgrade_early_bird(self) -> bool:
        """Silently upgrade today's early_bird entry if phone shows a workout."""
        try:
            status, message = self._verify_phone_workout()
        except (OSError, RuntimeError) as exc:
            _logger.info("Early bird upgrade phone check failed: %s", exc)
            return False
        if status != "verified":
            _logger.info(
                "Early bird upgrade skipped (phone status=%s): %s",
                status,
                message,
            )
            return False
        self.workout_data["type"] = "phone_verified"
        self.workout_data["source"] = message
        self.workout_data["after_early_bird"] = "true"
        self._adjust_shutdown_time_later()
        self.save_workout_log()
        return True
