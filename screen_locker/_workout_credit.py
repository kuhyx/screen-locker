"""Shared workout-credit logic: save + shutdown bonus + debt-clear.

Extracted from ``screen_lock.py`` so both the locked-screen flow
(``ScreenLocker.unlock_screen``) and the voluntary ``StatusWindow``
"Log Manual Workout" path apply the identical reward — the drift between
those two paths having different behavior once caused a real shutdown-bonus
miss (see ``project-lock-disabled-pending-manual-log`` memory).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING

from screen_locker import _sick_tracker
from screen_locker._weekly_check import (
    COUNTED_WORKOUT_TYPES,
    WEEKLY_WORKOUT_MINIMUM,
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
            "manual_workout",
        ):
            return None
        history = _sick_tracker.load_history()
        if history.debt <= 0:
            return 0
        new_debt = _sick_tracker.clear_one_debt(history)
        _sick_tracker.save_history(history)
        return new_debt

    def _was_already_counted_today(self) -> bool:
        """Check whether today's log entry, before this save, already counted.

        Used to guard :meth:`_apply_workout_credit` against double-crediting:
        unlike the locked flow (which only ever unlocks once), the voluntary
        ``StatusWindow`` entry point can save more than one workout on the
        same day (the manual-workout budget allows up to 2/week), and
        ``_adjust_shutdown_time_later`` is additive, not idempotent.
        """
        logs = self._load_existing_logs()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        entry = logs.get(today)
        if not isinstance(entry, dict):
            return False
        workout_data = entry.get("workout_data", {})
        return workout_data.get("type") in COUNTED_WORKOUT_TYPES

    def _apply_workout_credit(self) -> WorkoutCreditResult:
        """Persist ``workout_data`` and apply reward credit, once per day.

        Shared by the locked-screen flow (:meth:`ScreenLocker.unlock_screen`)
        and the voluntary ``StatusWindow`` "Log Manual Workout" path.
        """
        already_counted = self._was_already_counted_today()
        # sick_day is already persisted to sick_history.json by
        # _finalize_sick_day — workout_log.json is reserved for real outcomes.
        if self.workout_data.get("type") != "sick_day":
            self.save_workout_log()

        weekly_count = count_weekly_workouts(self.log_file)
        if already_counted:
            return WorkoutCreditResult(
                shutdown_adjusted=False,
                new_debt=None,
                extra_bonus_delta=0,
                weekly_count=weekly_count,
                already_counted_today=True,
            )

        shutdown_adjusted = self._try_adjust_shutdown_for_workout()
        new_debt = self._clear_debt_on_verified_workout()

        # Extra-workout bonus: +1h per workout above the weekly minimum.
        extra_bonus_delta = 0
        if weekly_count > WEEKLY_WORKOUT_MINIMUM:
            old_cfg = self._read_shutdown_config()
            if old_cfg and self._adjust_shutdown_time_by(1):
                new_cfg = self._read_shutdown_config()
                if new_cfg:
                    extra_bonus_delta = new_cfg[1] - old_cfg[1]

        return WorkoutCreditResult(
            shutdown_adjusted=shutdown_adjusted,
            new_debt=new_debt,
            extra_bonus_delta=extra_bonus_delta,
            weekly_count=weekly_count,
            already_counted_today=False,
        )
