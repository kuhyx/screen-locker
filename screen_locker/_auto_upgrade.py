"""Mixin: auto-upgrade early_bird/sick_day log entries via phone or RunnerUp."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import sys

from screen_locker._wake_state import has_workout_skip_today

_logger = logging.getLogger(__name__)


class AutoUpgradeMixin:
    """Handles today-state detection and silent log-entry upgrading.

    Relies on methods from EarlyBirdMixin, PhoneVerificationMixin,
    RunnerUpVerificationMixin, LogMixin, and ShutdownMixin via MRO.
    """

    def _is_sick_day_log(self) -> bool:
        """Check if today's workout log is a sick day (not yet verified)."""
        if not self.log_file.exists():  # type: ignore[attr-defined]
            return False
        try:
            with self.log_file.open() as f:  # type: ignore[attr-defined]
                logs = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        entry = logs.get(today)
        if entry is None:
            return False
        return entry.get("workout_data", {}).get("type") == "sick_day"

    def _check_early_exits(self, *, verify_only: bool) -> None:
        """Check startup conditions and exit early when appropriate."""
        if verify_only:
            if not self._is_sick_day_log():
                _logger.info("No sick day logged today. Nothing to verify.")
                sys.exit(0)
            return
        self._check_non_verify_exits()  # type: ignore[attr-defined]

    def _check_today_state_exits(self) -> bool:
        """Handle early-bird and today's log states. Return True to stop startup."""
        if (
            self._is_early_bird_log()  # type: ignore[attr-defined]
            and not self._is_early_bird_time()  # type: ignore[attr-defined]
        ):
            if self._try_auto_upgrade_early_bird():
                _logger.info("Auto-upgraded early_bird entry to phone_verified.")
                sys.exit(0)
                return True
            return False  # Expired early bird, upgrade unavailable — full lock.
        if self._is_early_bird_log():  # type: ignore[attr-defined]
            _logger.info("Early bird window still active — skipping lock.")
        elif self._is_sick_day_log() and self._try_auto_upgrade_sick_day():
            _logger.info("Auto-upgraded today's sick_day entry to phone_verified.")
        elif self.has_logged_today():  # type: ignore[attr-defined]
            _logger.info("Workout already logged today. Skipping screen lock.")
        elif has_workout_skip_today():
            _logger.info("Wake alarm earned workout skip. Skipping screen lock.")
        elif self._is_early_bird_time():  # type: ignore[attr-defined]
            self._save_early_bird_log()  # type: ignore[attr-defined]
            _logger.info("Early bird time — skipping lock, will re-check at 08:30.")
        else:
            return False
        sys.exit(0)
        return True

    def _try_auto_upgrade_sick_day(self) -> bool:
        """Upgrade sick_day entry when phone or RunnerUp detects a valid workout."""
        try:
            status, message = self._verify_phone_workout()  # type: ignore[attr-defined]
        except (OSError, RuntimeError) as exc:
            _logger.info("Auto-upgrade phone check failed: %s", exc)
            status, message = "error", str(exc)
        if status == "verified":
            self.workout_data["type"] = "phone_verified"  # type: ignore[attr-defined]
            self.workout_data["source"] = message  # type: ignore[attr-defined]
            self.workout_data["after_sick_day"] = "true"  # type: ignore[attr-defined]
            self._adjust_shutdown_time_later()  # type: ignore[attr-defined]
            self.save_workout_log()  # type: ignore[attr-defined]
            return True
        _logger.info("Auto-upgrade phone skipped (%s), trying RunnerUp...", status)
        try:
            runnerup_status, runnerup_msg = self._verify_runnerup_workout()  # type: ignore[attr-defined]
        except (OSError, RuntimeError) as exc:
            _logger.info("Auto-upgrade RunnerUp check failed: %s", exc)
            return False
        if runnerup_status != "verified":
            _logger.info(
                "Auto-upgrade RunnerUp skipped (%s): %s", runnerup_status, runnerup_msg
            )
            return False
        self.workout_data["type"] = "runnerup_verified"  # type: ignore[attr-defined]
        self.workout_data["source"] = runnerup_msg  # type: ignore[attr-defined]
        self.workout_data["after_sick_day"] = "true"  # type: ignore[attr-defined]
        self._adjust_shutdown_time_later()  # type: ignore[attr-defined]
        self.save_workout_log()  # type: ignore[attr-defined]
        return True

    def _try_auto_upgrade_early_bird(self) -> bool:
        """Try phone then RunnerUp to upgrade an early_bird log entry."""
        try:
            status, message = self._verify_phone_workout()  # type: ignore[attr-defined]
        except (OSError, RuntimeError) as exc:
            _logger.info("Early bird upgrade phone check failed: %s", exc)
            status, message = "error", str(exc)
        if status == "verified":
            self.workout_data["type"] = "phone_verified"  # type: ignore[attr-defined]
            self.workout_data["source"] = message  # type: ignore[attr-defined]
            self.workout_data["after_early_bird"] = "true"  # type: ignore[attr-defined]
            self._adjust_shutdown_time_later()  # type: ignore[attr-defined]
            self.save_workout_log()  # type: ignore[attr-defined]
            return True
        _logger.info("Early bird phone skipped (%s), trying RunnerUp...", status)
        try:
            runnerup_status, runnerup_msg = self._verify_runnerup_workout()  # type: ignore[attr-defined]
        except (OSError, RuntimeError) as exc:
            _logger.info("Early bird RunnerUp check failed: %s", exc)
            return False
        if runnerup_status != "verified":
            _logger.info(
                "Early bird RunnerUp skipped (%s): %s", runnerup_status, runnerup_msg
            )
            return False
        self.workout_data["type"] = "runnerup_verified"  # type: ignore[attr-defined]
        self.workout_data["source"] = runnerup_msg  # type: ignore[attr-defined]
        self.workout_data["after_early_bird"] = "true"  # type: ignore[attr-defined]
        self._adjust_shutdown_time_later()  # type: ignore[attr-defined]
        self.save_workout_log()  # type: ignore[attr-defined]
        return True
