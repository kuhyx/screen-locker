"""Mixin: auto-upgrade early_bird/sick_day pending states via phone or RunnerUp.

Neither early_bird (a same-day pending marker, see ``_early_bird.py``) nor
sick_day (tracked in ``sick_history.json`` via ``_sick_tracker.py``) live in
log.json — this module only checks their pending state and, on
success, writes the *real* outcome (phone_verified/runnerup_verified) there.

The upgrade credits through ``_apply_workout_credit`` -- save first, reward
only if the entry was actually appended. It used to push the shutdown hour
and THEN save: when the same run was already in the log (the 15-minute sync
pass had pulled the TCX at 20:25 on 2026-09-16) the save deduped to nothing
and the +2h landed anyway, and again on every 5-minute tick while the
pending marker lasted -- a runaway that only the 23:00 ceiling stopped.
"""

from __future__ import annotations

import logging
import sys

from screen_locker import _sick_tracker
from screen_locker._decision_log import LockDecision, record_decision
from screen_locker._decision_reasons import reasons_extra
from screen_locker._morning_session import has_workout_skip_today
from screen_locker._weekly_check import has_weekly_minimum, is_relaxed_day

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


class _ReasonsMixin:
    """Supplies the side-effect-free conditions that annotate a decision.

    The ladder below is first-match-wins, so only the acting reason was ever
    recorded. These predicates let a line also name the conditions that held
    but were never reached -- notably "the workout is already logged" hiding
    behind "the early-bird window is open".
    """

    def _other_conditions(self, acting: str) -> dict[str, object]:
        """Return the ``also=`` extra naming every other condition that holds.

        Strictly read-only. ``_try_auto_upgrade_*`` and
        ``_save_early_bird_pending`` are deliberately absent: they write log
        entries and state, and must never run to produce a log line.
        """
        return reasons_extra(
            acting,
            {
                "scheduled_skip_day": self._is_scheduled_skip_today,
                "early_bird_window_active": self._is_early_bird_pending,
                "sick_day": self._is_sick_day_today,
                "workout_logged_today": self.has_logged_today,
                "wake_alarm_skip": has_workout_skip_today,
                "relaxed_day": is_relaxed_day,
                "weekly_minimum_met": lambda: has_weekly_minimum(self.log_file),
            },
        )


class AutoUpgradeMixin(_ReasonsMixin):
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
        pending = self._is_early_bird_pending()
        window_open = self._is_early_bird_time()
        if pending and not window_open and self._try_auto_upgrade_early_bird():
            _skip(
                "early_bird_auto_upgraded",
                "Auto-upgraded early_bird entry to phone_verified.",
            )
            return True
        # An expired marker with nothing to upgrade is NOT a lock on its own.
        # It used to `return False` right here, ahead of has_logged_today, so
        # a workout logged by any other path after 08:30 never counted while
        # the marker lasted: on 2026-09-18 a manual walk entered on the lock
        # screen at 09:32 closed the lock, and the 09:35 tick locked again --
        # every 5 minutes, for the rest of the day -- while the explain chain
        # (_compliance_state, where the expired marker is non-terminal) said
        # "lock skipped". Fall through to the same ladder as any other morning.
        if pending and window_open:
            # The window is the wake-alarm carrot (see EarlyBirdMixin): it
            # closes when the signed exempt_until passes, and the 5-minute
            # tick plus early-bird-workout-check.timer then re-decide.
            _skip(
                "early_bird_window_active",
                f"Morning-session carrot still in force: {self._morning_skip}.",
                recheck_by="workout-locker.timer",
                **self._other_conditions("early_bird_window_active"),
            )
        elif self._is_sick_day_today():
            if self._try_auto_upgrade_sick_day():
                _skip(
                    "sick_day_auto_upgraded",
                    "Auto-upgraded today's sick_day entry to phone_verified.",
                )
            else:
                _skip(
                    "sick_day",
                    "Sick day already logged today.",
                    **self._other_conditions("sick_day"),
                )
        elif self.has_logged_today():
            _skip(
                "workout_logged_today",
                "Workout already logged today.",
                **self._other_conditions("workout_logged_today"),
            )
        elif window_open:
            # Bank the marker so the run that sees the carrot end tries a
            # phone/RunnerUp workout before falling through to a lock.
            self._save_early_bird_pending()
            skip = self._morning_skip
            _skip(
                "wake_alarm_skip",
                f"Morning session earned it: {skip or 'carrot in force'}.",
                exempt_until=skip.exempt_until.isoformat() if skip else None,
                outcome=skip.outcome if skip else None,
                **self._other_conditions("wake_alarm_skip"),
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
            self._apply_workout_credit()
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
        self._apply_workout_credit()
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
            self._apply_workout_credit()
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
        self._apply_workout_credit()
        return True
