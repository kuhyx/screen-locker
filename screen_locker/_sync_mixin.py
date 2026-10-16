"""Manual-workout sync and RunnerUp auto-fill for the screen locker.

Split out of ``screen_lock.py`` to keep every file under the 250-line cap.
These methods form one cohesive unit: they publish this PC's workouts, ingest
records other devices produced, and apply the same shutdown credit a
live-logged workout earns.
"""

from __future__ import annotations

import logging

from screen_locker._constants import SHUTDOWN_BASE_FILE
from screen_locker._earned import span
from screen_locker._earner_units import sync_path_unit
from screen_locker._manual_pending import local_pending_records
from screen_locker._manual_push import push_pc_workouts
from screen_locker._manual_sync import ingest_manual_records
from screen_locker._session_sync import ingest_session_records
from screen_locker._shutdown_base import apply_flat_bonuses_if_new
from screen_locker._workout_sync import (
    pull_all_manual_records,
    pull_all_session_records,
)

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
        self._ingest_synced_sessions()
        self._auto_fill_week_runnerup_bonus()
        # Same reason: a LeetCode solve or a reading session made after login
        # must not wait for the next login to earn its hour.
        apply_flat_bonuses_if_new(SHUTDOWN_BASE_FILE, self)
        # The ledger watch that makes that pass instant follows the registry.
        sync_path_unit()

    def _ingest_synced_manual_workouts(self) -> None:
        """Sync manual workouts: publish this PC's, ingest everyone else's.

        Each newly-ingested record earns the identical shutdown reward a
        live-logged workout would (see
        ``WorkoutCreditMixin._apply_credit_for_written_entry``), regardless of
        whether it's dated today or back-dated — there's only one current
        shutdown config, so a back-dated sync still pushes it. A record dated
        after today is deferred by the ingest (nothing credited, nothing in
        ``log.json``) and picked up by the first pass on its date -- which the
        startup checks run before any lock decision.
        """
        push_pc_workouts(self.log_file)
        pulled = pull_all_manual_records()
        seen = {record_id for record_id, _payload in pulled}
        # This PC's own future-dated entries come back through the pull (the PC
        # ingests its own device log), but when Firebase is down on their day
        # the ledger is the only copy -- so it is a source here too.
        local = [rec for rec in local_pending_records() if rec[0] not in seen]
        ingested = ingest_manual_records(
            self.log_file,
            [*pulled, *local],
            on_ingested=self._credit_ingested_workout,
        )
        for record_id in ingested:
            _logger.info("Ingested synced manual workout: %s", record_id)
        self.workout_data = {}

    def _ingest_due_local_manual_workouts(self) -> None:
        """Ingest this PC's own future-dated entries whose day has come.

        Local-only (no network), so the new-day reset pass on the poke path
        can run it without costing the phone's instant credit a Firebase
        round trip. Entries not yet due are deferred by the ingest itself.
        """
        ingested = ingest_manual_records(
            self.log_file,
            local_pending_records(),
            on_ingested=self._credit_ingested_workout,
        )
        for record_id in ingested:
            _logger.info("Ingested due scheduled manual workout: %s", record_id)
        self.workout_data = {}

    def _ingest_synced_sessions(self) -> None:
        """Ingest StrongLifts sessions other devices (or this PC) finished.

        The desktop build of workout_app writes a session to its own device
        log and nothing else; without this the record would only ever be seen
        by the interactive verification flow, so a workout finished on the PC
        earned nothing until a lock screen happened to open.

        Each newly-ingested session earns the identical reward a live-logged
        workout would, and re-running is a no-op (the write chokepoint dedups
        by workout_id).
        """
        ingested = ingest_session_records(
            self.log_file,
            pull_all_session_records(),
            on_ingested=self._credit_ingested_workout,
        )
        for record_id in ingested:
            _logger.info("Ingested synced StrongLifts session: %s", record_id)
        self.workout_data = {}

    def _credit_ingested_workout(
        self, entry: dict[str, str], prior_entries: list[dict]
    ) -> None:
        """Apply the live-workout reward to a workout ingested from another source.

        Shared by manual-workout sync, StrongLifts session sync and the
        RunnerUp TCX backfill -- one reward rule for every non-interactive way
        a workout can land in the log.
        """
        self.workout_data = entry
        credit = self._apply_credit_for_written_entry(prior_entries)
        if credit.shutdown_adjusted:
            _logger.info(
                "Ingested workout pushed shutdown time later: %s",
                entry.get("source", ""),
            )
        elif credit.extra_bonus_delta:
            _logger.info(
                "Ingested workout added +%s shutdown time: %s",
                span(credit.extra_bonus_delta),
                entry.get("source", ""),
            )

    def _auto_fill_week_runnerup_bonus(self) -> None:
        """Auto-fill missed RunnerUp workouts and credit each one.

        Every appended run goes through the same
        :meth:`_credit_ingested_workout` callback as a synced manual workout
        or StrongLifts session, so the reward is the documented day rule
        (+2h first counted workout of its day, +1h each further one).
        """
        n_filled = self._scan_and_fill_week_runnerup(
            self.log_file, on_ingested=self._credit_ingested_workout
        )
        if n_filled:
            _logger.info(
                "Auto-filled %d RunnerUp workout(s) from TCX exports.", n_filled
            )
        self.workout_data = {}
