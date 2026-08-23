"""Startup early-exit checks for the screen locker.

Split out of ``screen_lock.py`` to keep every file under the 250-line cap.
These run before any lock window is built and decide whether the lock is
needed at all: scheduled skip, weekly minimum already met, relaxed day, or
genuine extreme heat.

The entry point is ``_check_non_verify_exits``, which
``_auto_upgrade.AutoUpgradeMixin._check_early_exits`` calls.
"""

from __future__ import annotations

import logging
import sys

from screen_locker._compliance_predicates import is_relaxed_day_skipped_today
from screen_locker._constants import (
    EXTRA_BENEFITS_FILE,
    HEAT_SKIP_CITY,
    HEAT_SKIP_TEMP_THRESHOLD,
    SHUTDOWN_BASE_FILE,
    SICK_DAY_STATE_FILE,
)
from screen_locker._decision_log import (
    LockDecision,
    record_decision,
)
from screen_locker._extra_benefits import process_week_transition
from screen_locker._shutdown_base import reset_to_base_if_new_day
from screen_locker._sync_mixin import SyncMixin
from screen_locker._temperature import fetch_current_temp_with_status
from screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
    has_weekly_minimum,
    is_relaxed_day,
)

__all__ = ["StartupChecksMixin"]

_logger = logging.getLogger(__name__)


class StartupChecksMixin(SyncMixin):
    """Decide, before building any UI, whether the lock should run today.

    Inherits ``SyncMixin`` rather than sitting beside it in ``ScreenLocker``'s
    base list: the early-exit sequence calls ``_ingest_synced_manual_workouts``
    and ``_auto_fill_week_runnerup_bonus`` directly, so the dependency is real
    and this keeps the god-class's ancestor count from growing.
    """

    def _record_decision(
        self, *, locked: bool, reason: str, detail: str, **extra: object
    ) -> None:
        """Record one lock decision, annotated with this week's progress.

        The weekly count is attached to every decision because "was it right to
        skip?" is unanswerable without it -- during the 2026-08 outage the
        journal could not distinguish "5/5, correctly skipped" from "0/5, should
        have locked".
        """
        record_decision(
            LockDecision(
                locked=locked,
                reason=reason,
                detail=detail,
                weekly_count=count_weekly_workouts(self.log_file),
                weekly_required=WEEKLY_WORKOUT_MINIMUM,
                # Annotate with the conditions this first-match-wins ladder
                # never reached, so "why not lock?" is answerable from the one
                # line rather than by re-deriving the ladder by hand.
                extra={**self._other_conditions(reason), **extra},
            )
        )

    def _record_skip(self, reason: str, detail: str, **extra: object) -> None:
        """Record a decision not to enforce, then exit the process."""
        self._record_decision(locked=False, reason=reason, detail=detail, **extra)
        sys.exit(0)

    def _check_non_verify_exits(self) -> None:
        """Check all normal (non-verify) startup early-exit conditions."""
        if self._is_scheduled_skip_today():
            self._record_skip("scheduled_skip_day", "Today is a scheduled skip day.")
            return
        # Award streak / shutdown-bonus / EB-extension rewards from last week
        # before the daily reset, so a Monday transition's bonus is recorded
        # in time for _apply_weekly_shutdown_bonus below to see it.
        for reward_msg in process_week_transition(self.log_file, EXTRA_BENEFITS_FILE):
            _logger.info("Weekly reward: %s", reward_msg)
        # Reset shutdown config to base (21:00) at the start of each new day,
        # then layer this week's earned bonus back on top of the fresh base.
        if reset_to_base_if_new_day(
            SHUTDOWN_BASE_FILE, self, sick_day_state_file=SICK_DAY_STATE_FILE
        ):
            self._apply_weekly_shutdown_bonus()
        # Ingest any manual workouts synced from the phone (or another device)
        # before the early-exit checks, so a manual logged off-app still counts
        # toward today's/this week's minimum.
        self._ingest_synced_manual_workouts()
        # Auto-fill any RunnerUp workouts from earlier in the current ISO week
        # before any early-exit check, so gaps are closed regardless of today's
        # logged state (early_bird, sick_day, etc.).
        self._auto_fill_week_runnerup_bonus()
        if self._check_today_state_exits():
            return
        # Day-of-week routing: Tue/Wed/Thu relaxed (optional), Fri-Mon enforced.
        if is_relaxed_day():
            # The recurring 30-minute workout-locker.timer re-derives
            # relaxed_day from scratch every tick, so without this check a
            # dismissal via "Skip — No Penalty" would be forgotten by the very
            # next run and the prompt would reappear.
            if is_relaxed_day_skipped_today(self.log_file):
                self._record_skip(
                    "relaxed_day_already_skipped",
                    "Relaxed day already dismissed via Skip — No Penalty today.",
                )
                return
            self._record_decision(
                locked=False,
                reason="relaxed_day",
                detail="Relaxed day (Tue-Thu) — showing the optional prompt.",
            )
            self._relaxed_day_mode = True
            return
        # Fri-Mon: skip lock when weekly minimum is already met.
        if has_weekly_minimum(self.log_file):
            self._record_skip(
                "weekly_minimum_met",
                f"Weekly minimum of {WEEKLY_WORKOUT_MINIMUM} workouts met.",
            )
            return
        # Only remaining same-day skip: genuine extreme heat. Sick days go
        # through the justification flow instead; there is no banked
        # "skip a workout" credit — that mechanic works against the goal of
        # maximizing weekly workouts, so it was removed in favor of a
        # shutdown-time-only reward (see _apply_weekly_shutdown_bonus).
        self._check_heat_skip_exit()
        # Nothing excused today: falling through here means the lock WILL be
        # built. Recorded explicitly so the trail shows enforcement happening,
        # not merely the absence of a skip -- "no line at all" was precisely
        # the signature of the 2026-08 outage.
        self._record_decision(
            locked=True,
            reason="enforced",
            detail="No exemption applied — building the lock screen.",
        )

    def _check_heat_skip_exit(self) -> None:
        """Exit early if today qualifies for the extreme-heat skip dialog.

        Fail-closed by construction: a failed or timed-out temperature fetch
        falls straight through to the lock, same as "not hot enough" — the
        only difference is this logs *why* explicitly, so a fetch failure
        is never silently indistinguishable from a normal day in the logs.
        """
        check = fetch_current_temp_with_status(HEAT_SKIP_CITY)
        if check.timed_out:
            _logger.warning(
                "Heat-skip temperature check timed out — defaulting to lock."
            )
            return
        if check.temp_celsius is None:
            _logger.warning(
                "Heat-skip temperature check failed (network/API error) — "
                "defaulting to lock."
            )
            return
        if check.temp_celsius < HEAT_SKIP_TEMP_THRESHOLD:
            return
        _logger.info(
            "Temperature %.0f°C exceeds threshold — showing heat-skip dialog.",
            check.temp_celsius,
        )
        if self._show_heat_skip_dialog(check.temp_celsius):
            self._save_heat_skip_log(check.temp_celsius)
            self._record_skip(
                "heat_skip",
                f"User skipped the workout due to heat ({check.temp_celsius:.0f}°C).",
                temp_celsius=round(check.temp_celsius, 1),
            )
