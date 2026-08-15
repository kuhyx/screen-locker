"""Manual-workout sync and RunnerUp auto-fill for the screen locker.

Split out of ``screen_lock.py`` to keep every file under the 250-line cap.
These methods form one cohesive unit: they publish this PC's workouts, ingest
records other devices produced, and apply the same shutdown/debt credit a
live-logged workout earns.
"""

from __future__ import annotations

import logging

from screen_locker._constants import EXTRA_BENEFITS_FILE
from screen_locker._extra_benefits import weekly_shutdown_bonus_hours
from screen_locker._manual_push import push_pc_workouts
from screen_locker._manual_sync import ingest_manual_records
from screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
)
from screen_locker._workout_sync import pull_all_manual_records

__all__ = ["SyncMixin"]

_logger = logging.getLogger(__name__)


class SyncMixin:
    """Publish, ingest and credit manual workouts synced between devices."""

    def sync_now(self) -> None:
        """Run one sync pass: publish this PC's workouts, ingest everyone's.

        The public entry point behind ``--sync-only``, which the
        ``workout-sync.timer`` unit calls. Sync used to happen only inside the
        locker's startup path, so a workout finished after login stayed
        invisible until the next login.

        Also re-runs the RunnerUp TCX backfill here, not just at login: the
        login-time scan gets exactly one shot, and if the phone isn't
        adb-visible at that instant (e.g. USB debugging not yet
        authorized), a same-day run stays uncredited until the next login.
        Repeating it every 15 minutes closes that gap.
        """
        self._ingest_synced_manual_workouts()
        self._auto_fill_week_runnerup_bonus()

    def _ingest_synced_manual_workouts(self) -> None:
        """Sync manual workouts: publish this PC's, ingest everyone else's.

        Each newly-ingested record earns the identical shutdown/debt reward a
        live-logged workout would (see
        ``WorkoutCreditMixin._apply_credit_for_written_entry``), regardless of
        whether it's dated today or back-dated — there's only one current
        shutdown config, so a back-dated sync still pushes it.
        """
        push_pc_workouts(self.log_file)
        ingested = ingest_manual_records(
            self.log_file,
            pull_all_manual_records(),
            on_ingested=self._credit_ingested_manual_workout,
        )
        for record_id in ingested:
            _logger.info("Ingested synced manual workout: %s", record_id)
        self.workout_data = {}

    def _credit_ingested_manual_workout(
        self, entry: dict[str, str], prior_entries: list[dict]
    ) -> None:
        """Apply the live-workout reward to a manual workout ingested via sync."""
        self.workout_data = entry
        credit = self._apply_credit_for_written_entry(prior_entries)
        if credit.shutdown_adjusted:
            _logger.info(
                "Synced manual workout pushed shutdown time +2h: %s",
                entry.get("source", ""),
            )
        elif credit.extra_bonus_delta:
            _logger.info(
                "Synced manual workout added +%dh shutdown time: %s",
                credit.extra_bonus_delta,
                entry.get("source", ""),
            )

    def _auto_fill_week_runnerup_bonus(self) -> None:
        """Auto-fill missed RunnerUp workouts and award any earned bonus."""
        prev_count = count_weekly_workouts(self.log_file)
        n_filled = self._scan_and_fill_week_runnerup(self.log_file)
        if not n_filled:
            return
        new_count = count_weekly_workouts(self.log_file)
        _logger.info("Auto-filled %d RunnerUp workout(s) from TCX exports.", n_filled)
        # Award +1h for each newly auto-filled workout above the minimum.
        bonus = max(0, new_count - max(WEEKLY_WORKOUT_MINIMUM, prev_count))
        if bonus > 0 and self._adjust_shutdown_time_by(bonus):
            _logger.info("Auto-fill extra bonus: +%dh shutdown time.", bonus)

    def _apply_weekly_shutdown_bonus(self) -> None:
        """Layer this week's earned shutdown bonus back on top of the fresh base."""
        bonus = weekly_shutdown_bonus_hours(EXTRA_BENEFITS_FILE)
        if bonus > 0 and self._adjust_shutdown_time_by(bonus):
            _logger.info("Weekly bonus: +%dh shutdown time this week.", bonus)
