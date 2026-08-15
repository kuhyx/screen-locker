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

from screen_locker._constants import (
    EXTRA_BENEFITS_FILE,
    HEAT_SKIP_CITY,
    HEAT_SKIP_TEMP_THRESHOLD,
    SHUTDOWN_BASE_FILE,
    SICK_DAY_STATE_FILE,
)
from screen_locker._extra_benefits import process_week_transition
from screen_locker._shutdown_base import reset_to_base_if_new_day
from screen_locker._sync_mixin import SyncMixin
from screen_locker._temperature import fetch_current_temp_with_status
from screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM,
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

    def _check_non_verify_exits(self) -> None:
        """Check all normal (non-verify) startup early-exit conditions."""
        if self._is_scheduled_skip_today():
            _logger.info("Today is a scheduled skip day. Skipping screen lock.")
            sys.exit(0)
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
            _logger.info("Relaxed day (Tue-Thu) - showing optional workout prompt.")
            self._relaxed_day_mode = True
            return
        # Fri-Mon: skip lock when weekly minimum is already met.
        if has_weekly_minimum(self.log_file):
            _logger.info(
                "Weekly minimum of %d workouts met. Skipping screen lock.",
                WEEKLY_WORKOUT_MINIMUM,
            )
            sys.exit(0)
            return
        # Only remaining same-day skip: genuine extreme heat. Sick days go
        # through the justification flow instead; there is no banked
        # "skip a workout" credit — that mechanic works against the goal of
        # maximizing weekly workouts, so it was removed in favor of a
        # shutdown-time-only reward (see _apply_weekly_shutdown_bonus).
        self._check_heat_skip_exit()

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
            _logger.info(
                "User skipped workout due to heat (%.0f°C).", check.temp_celsius
            )
            sys.exit(0)
