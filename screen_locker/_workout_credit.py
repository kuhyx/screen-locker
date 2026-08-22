"""Shared workout-credit logic: save + shutdown bonus + debt-clear.

Extracted from ``screen_lock.py`` so both the locked-screen flow
(``ScreenLocker.unlock_screen``) and the voluntary ``StatusWindow``
"Log Manual Workout" path apply the identical reward — the drift between
those two paths having different behavior once caused a real shutdown-bonus
miss (see ``project-lock-disabled-pending-manual-log`` memory).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from screen_locker import _sick_tracker
from screen_locker._weekly_check import (
    COUNTED_WORKOUT_TYPES,
    PC_WORKOUT_TYPE,
    count_weekly_workouts,
)

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkoutCreditResult:
    """Outcome of :meth:`WorkoutCreditMixin._apply_workout_credit`."""

    shutdown_adjusted: bool
    new_debt: int | None
    extra_bonus_delta: int
    weekly_count: int
    already_counted_today: bool


class WorkoutCreditMixin:
    """Save a workout entry and apply its shutdown/debt/extra-bonus reward.

    Requires ``self.workout_data``, ``self.log_file``, and the ``LogMixin``/
    ``ShutdownMixin`` methods it calls into.
    """

    workout_data: dict[str, str]
    log_file: Path

    def _try_adjust_shutdown_for_workout(self) -> bool:
        """Try to adjust shutdown time later for actual workouts."""
        workout_type = self.workout_data.get("type", "")
        if workout_type not in COUNTED_WORKOUT_TYPES:
            return False
        adjusted = self._adjust_shutdown_time_later()
        if adjusted:
            _logger.info("Shutdown time moved 2 hours later as workout reward")
        return adjusted

    def _clear_debt_on_verified_workout(self) -> int | None:
        """Decrement workout debt by one for a verified workout.

        Returns the new debt count, or ``None`` when this wasn't a
        phone-verified workout.
        """
        if self.workout_data.get("type") not in (
            "phone_verified",
            "runnerup_verified",
            PC_WORKOUT_TYPE,
            "manual_workout",
        ):
            return None
        history = _sick_tracker.load_history()
        if history.debt <= 0:
            return 0
        new_debt = _sick_tracker.clear_one_debt(history)
        _sick_tracker.save_history(history)
        return new_debt

    def _apply_credit_for_written_entry(
        self, prior_entries: list[dict]
    ) -> WorkoutCreditResult:
        """Apply the shutdown/debt reward for an already-written ``workout_data``.

        Shared by :meth:`_apply_workout_credit` (the live locked-screen,
        Status-Window, and Check-Phone paths, which always write under today)
        and the manual-sync ingestion path
        (:func:`screen_locker._manual_sync.ingest_manual_records`, via its
        ``on_ingested`` callback — which writes under the entry's own date,
        today or back-dated). ``prior_entries`` must be that entry's day's
        entries *before* it, so "first counted workout of the day" is
        evaluated relative to the entry's own date; the shutdown adjustment
        itself always lands on the current shutdown config, since there's
        only ever one "tonight" to push regardless of which day earned it.

        Rewards:

        * first counted workout of the day → base **+2h** (cap 23:00);
        * an additional same-day counted workout (verified OR manual) →
          **+1h** (cap midnight) — manual workouts stack exactly like
          verified ones; the manual-workout rate budget is the only limiter.
        """
        weekly_count = count_weekly_workouts(self.log_file)
        first_counted_today = not any(
            entry.get("workout_data", {}).get("type") in COUNTED_WORKOUT_TYPES
            for entry in prior_entries
        )

        shutdown_adjusted = False
        extra_bonus_delta = 0
        if first_counted_today:
            shutdown_adjusted = self._try_adjust_shutdown_for_workout()
        elif self.workout_data.get("type") in COUNTED_WORKOUT_TYPES:
            old_cfg = self._read_shutdown_config()
            if old_cfg and self._adjust_shutdown_time_by(1):
                new_cfg = self._read_shutdown_config()
                if new_cfg:
                    extra_bonus_delta = new_cfg[1] - old_cfg[1]

        new_debt = self._clear_debt_on_verified_workout()

        return WorkoutCreditResult(
            shutdown_adjusted=shutdown_adjusted,
            new_debt=new_debt,
            extra_bonus_delta=extra_bonus_delta,
            weekly_count=weekly_count,
            already_counted_today=False,
        )

    def _apply_workout_credit(self) -> WorkoutCreditResult:
        """Append ``workout_data`` and apply its reward, scaled to the day.

        Shared by the locked-screen flow (:meth:`ScreenLocker.unlock_screen`),
        the voluntary ``StatusWindow`` "Log Manual Workout" path, and the
        Check-Phone verify path. Always files under *today*; see
        :meth:`_apply_credit_for_written_entry` for the shared reward logic
        (a duplicate — same ``workout_id`` already logged — earns no new
        credit).
        """
        # sick_day is already persisted to sick_history.json by
        # _finalize_sick_day — log.json is reserved for real outcomes.
        if self.workout_data.get("type") == "sick_day":
            return WorkoutCreditResult(
                shutdown_adjusted=False,
                new_debt=None,
                extra_bonus_delta=0,
                weekly_count=count_weekly_workouts(self.log_file),
                already_counted_today=False,
            )

        result = self.save_workout_log()

        if not result.appended:
            # A workout with this id was already recorded today — idempotent.
            return WorkoutCreditResult(
                shutdown_adjusted=False,
                new_debt=None,
                extra_bonus_delta=0,
                weekly_count=count_weekly_workouts(self.log_file),
                already_counted_today=True,
            )

        return self._apply_credit_for_written_entry(result.prior_entries)
