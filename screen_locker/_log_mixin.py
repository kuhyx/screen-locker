"""Mixin: workout log persistence (read/write workout_log.json)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac

from screen_locker import _compliance_state
from screen_locker._constants import SCHEDULED_SKIPS_FILE

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_logger = logging.getLogger(__name__)


class LogMixin:
    """Handles reading and writing workout_log.json for the ScreenLocker.

    ``log_file``/``workout_data`` are declared here (not assigned) so mypy
    knows their types on any composing class without needing
    ``type: ignore[attr-defined]`` on every access — the real values are set
    by ``ScreenLocker.__init__``.
    """

    log_file: Path
    workout_data: Mapping[str, object]

    def has_logged_today(self) -> bool:
        """Check if workout has been logged today with valid HMAC."""
        return _compliance_state.has_logged_today(self.log_file)

    def _load_existing_logs(self) -> dict:
        """Load existing workout logs from file."""
        if not self.log_file.exists():
            return {}
        try:
            with self.log_file.open() as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _is_scheduled_skip_today(self) -> bool:
        """Return True if today's date is listed in the scheduled skips file."""
        return _compliance_state.is_scheduled_skip_today(SCHEDULED_SKIPS_FILE)

    def save_workout_log(self) -> None:
        """Save workout data to log file with HMAC signature."""
        logs = self._load_existing_logs()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        entry: dict[str, object] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "workout_data": self.workout_data,
        }
        signature = compute_entry_hmac(entry)
        if signature is not None:
            entry["hmac"] = signature
        else:
            _logger.warning("HMAC key unavailable — saving unsigned entry")
        logs[today] = entry
        try:
            with self.log_file.open("w") as f:
                json.dump(logs, f, indent=2)
        except OSError as e:
            _logger.warning("Could not save workout log: %s", e)
