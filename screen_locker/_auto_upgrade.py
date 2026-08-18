"""Mixin: auto-upgrade early_bird/sick_day pending states via phone or RunnerUp.

Neither early_bird (a same-day pending marker, see ``_early_bird.py``) nor
sick_day (tracked in ``sick_history.json`` via ``_sick_tracker.py``) live in
log.json — this module only checks their pending state and, on
success, writes the *real* outcome (phone_verified/runnerup_verified) there.
"""

from __future__ import annotations

import logging
import sys

from screen_locker import _sick_tracker
from screen_locker._decision_log import LockDecision, record_decision
from screen_locker._wake_state import has_workout_skip_today

_logger = logging.getLogger(__name__)


def _skip(reason: str, detail: str, **extra: object) -> None:
    """Record a decision NOT to enforce, then exit.

    Every branch that abandons enforcement goes through here. Before this
    existed each one just logged at INFO and called ``sys.exit(0)``, which is
    how the locker managed to stop enforcing for thirteen days without leaving
    a single line saying so.
    """
    record_decision(
        LockDecision(locked=False, reason=reason, detail=detail, extra=extra)
    )
    sys.exit(0)


class AutoUpgradeMixin:
    """Handles today-state detection and silent log-entry upgrading.

    Relies on methods from EarlyBirdMixin, PhoneVerificationMixin,
    RunnerUpVerificationMixin, LogMixin, and ShutdownMixin via MRO.
    """

    def _is_sick_day_today(self) -> bool:
        """Check if today is marked as a sick day in sick_history.json."""
        return _sick_tracker.is_sick_day(_sick_tracker.load_history())

    def _check_early_exits(self, *, verify_only: bool) -> None:
        """Check startup conditions and exit early when appropriate."""
        if verify_only:
            if not self._is_sick_day_today():
                _skip("no_sick_day_to_verify", "No sick day logged today.")
            return
        self._check_non_verify_exits()

    def _check_today_state_exits(self) -> bool:
        """Handle early-bird and today's log states. Return True to stop startup."""
        if self._is_early_bird_pending() and not self._is_early_bird_time():
            if self._try_auto_upgrade_early_bird():
                _skip(
                    "early_bird_auto_upgraded",
                    "Auto-upgraded early_bird entry to phone_verified.",
                )
                return True
            return False  # Expired early bird, upgrade unavailable — full lock.
        if self._is_early_bird_pending():
            # The ONLY thing that closes this window is
            # early-bird-workout-check.timer. When that timer was disabled by an
            # ordering cycle (2026-08-04) this branch silently deferred the lock
            # every single day, forever.
            _skip(
                "early_bird_window_active",
                "Early bird window still active — deferring to the 08:30/09:05 "
                "re-check timer.",
                recheck_by="early-bird-workout-check.timer",
            )
        elif self._is_sick_day_today():
            if self._try_auto_upgrade_sick_day():
                _skip(
                    "sick_day_auto_upgraded",
                    "Auto-upgraded today's sick_day entry to phone_verified.",
                )
            else:
                _skip("sick_day", "Sick day already logged today.")
        elif self.has_logged_today():
            _skip("workout_logged_today", "Workout already logged today.")
        elif has_workout_skip_today():
            _skip("wake_alarm_skip", "Wake alarm earned a workout skip.")
        elif self._is_early_bird_time():
            self._save_early_bird_pending()
            _skip(
                "early_bird_banked",
                "Early bird time — banked the pending marker, will re-check "
                "at 08:30/09:05.",
                recheck_by="early-bird-workout-check.timer",
            )
        else:
            return False
        return True

    def _try_auto_upgrade_sick_day(self) -> bool:
        """Upgrade sick_day entry when phone or RunnerUp detects a valid workout."""
        try:
            status, message = self._verify_phone_workout()
        except (OSError, RuntimeError) as exc:
            _logger.warning(
                "Sick-day auto-upgrade could not reach the phone (%s) — today's "
                "sick_day entry stays unverified; trying RunnerUp next",
                exc,
            )
            status, message = "error", str(exc)
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            self.workout_data["after_sick_day"] = "true"
            self._adjust_shutdown_time_later()
            self.save_workout_log()
            return True
        _logger.info("Auto-upgrade phone skipped (%s), trying RunnerUp...", status)
        try:
            runnerup_status, runnerup_msg = self._verify_runnerup_workout()
        except (OSError, RuntimeError) as exc:
            _logger.warning(
                "Sick-day auto-upgrade could not read RunnerUp either (%s) — "
                "today stays a sick_day, NOT upgraded to a verified workout",
                exc,
            )
            return False
        if runnerup_status != "verified":
            _logger.info(
                "Auto-upgrade RunnerUp skipped (%s): %s", runnerup_status, runnerup_msg
            )
            return False
        self.workout_data["type"] = "runnerup_verified"
        self.workout_data["source"] = runnerup_msg
        self.workout_data["after_sick_day"] = "true"
        self._adjust_shutdown_time_later()
        self.save_workout_log()
        return True

    def _try_auto_upgrade_early_bird(self) -> bool:
        """Try phone then RunnerUp to upgrade an early_bird log entry."""
        try:
            status, message = self._verify_phone_workout()
        except (OSError, RuntimeError) as exc:
            _logger.warning(
                "Early-bird auto-upgrade could not reach the phone (%s) — the "
                "early_bird entry stays unverified; trying RunnerUp next",
                exc,
            )
            status, message = "error", str(exc)
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            self.workout_data["after_early_bird"] = "true"
            self._adjust_shutdown_time_later()
            self.save_workout_log()
            return True
        _logger.info("Early bird phone skipped (%s), trying RunnerUp...", status)
        try:
            runnerup_status, runnerup_msg = self._verify_runnerup_workout()
        except (OSError, RuntimeError) as exc:
            _logger.warning(
                "Early-bird auto-upgrade could not read RunnerUp either (%s) — "
                "the expired early_bird entry is NOT upgraded, so the screen "
                "will lock",
                exc,
            )
            return False
        if runnerup_status != "verified":
            _logger.info(
                "Early bird RunnerUp skipped (%s): %s", runnerup_status, runnerup_msg
            )
            return False
        self.workout_data["type"] = "runnerup_verified"
        self.workout_data["source"] = runnerup_msg
        self.workout_data["after_early_bird"] = "true"
        self._adjust_shutdown_time_later()
        self.save_workout_log()
        return True
