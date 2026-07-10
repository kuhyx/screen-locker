#!/usr/bin/env python3
"""Screen locker with workout verification for Arch Linux / i3wm.

Requires user to log their workout to unlock the screen.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import GateRoot, LockConfig, LockWindow

from screen_locker._auto_upgrade import AutoUpgradeMixin
from screen_locker._constants import (
    EARLY_BIRD_END_HOUR,
    EARLY_BIRD_END_MINUTE,
    EARLY_BIRD_START_HOUR,
    EXTRA_BENEFITS_FILE,
    HEAT_SKIP_CITY,
    HEAT_SKIP_TEMP_THRESHOLD,
    HMAC_KEY_FILE,
    MAX_CLOCK_SKEW_SECONDS,
    MIN_WORKOUT_DURATION_MINUTES,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    SCHEDULED_SKIPS_FILE,
    SHUTDOWN_BASE_FILE,
    SICK_DAY_STATE_FILE,
    SICK_LOCKOUT_SECONDS,
)
from screen_locker._early_bird import EarlyBirdMixin
from screen_locker._extra_benefits import (
    current_streak,
    process_week_transition,
    weekly_shutdown_bonus_hours,
)
from screen_locker._heat_skip import HeatSkipMixin
from screen_locker._log_mixin import LogMixin
from screen_locker._manual_workout_dialog import ManualWorkoutDialogMixin
from screen_locker._phone_verification import PhoneVerificationMixin
from screen_locker._runnerup_verification import RunnerUpVerificationMixin
from screen_locker._shutdown import ShutdownMixin
from screen_locker._shutdown_base import reset_to_base_if_new_day
from screen_locker._sick_dialog import SickDialogMixin
from screen_locker._temperature import fetch_current_temp_with_status
from screen_locker._ui_flows import UIFlowsMixin
from screen_locker._ui_flows_relaxed import UIFlowsRelaxedMixin
from screen_locker._ui_widgets import UIWidgetsMixin
from screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
    has_weekly_minimum,
    is_relaxed_day,
)
from screen_locker._window_setup import WindowSetupMixin
from screen_locker._workout_credit import WorkoutCreditMixin

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

__all__ = [
    "EARLY_BIRD_END_HOUR",
    "EARLY_BIRD_END_MINUTE",
    "EARLY_BIRD_START_HOUR",
    "HMAC_KEY_FILE",
    "MAX_CLOCK_SKEW_SECONDS",
    "MIN_WORKOUT_DURATION_MINUTES",
    "PHONE_PENALTY_DELAY_DEMO",
    "PHONE_PENALTY_DELAY_PRODUCTION",
    "SCHEDULED_SKIPS_FILE",
    "SICK_LOCKOUT_SECONDS",
    "WEEKLY_WORKOUT_MINIMUM",
    "ScreenLocker",
]

_logger = logging.getLogger(__name__)


def _assert_not_under_pytest() -> None:
    """Raise if the screen locker is being created inside a pytest run.

    Defence-in-depth: prevents a real fullscreen Tk window from locking
    the user's screen when tests forget to mock ``tk.Tk``.
    The check is cheap (one dict lookup) and only fires during testing.
    """
    if "pytest" in sys.modules and getattr(tk, "__name__", "") == "tkinter":
        msg = (
            "SAFETY: ScreenLocker.__init__ called under pytest with "
            "real tkinter — tk.Tk is not mocked"
        )
        raise RuntimeError(msg)


class ScreenLocker(
    AutoUpgradeMixin,
    EarlyBirdMixin,
    HeatSkipMixin,
    LogMixin,
    ManualWorkoutDialogMixin,
    WindowSetupMixin,
    WorkoutCreditMixin,
    ShutdownMixin,
    PhoneVerificationMixin,
    RunnerUpVerificationMixin,
    SickDialogMixin,
    UIFlowsMixin,
    UIFlowsRelaxedMixin,
    UIWidgetsMixin,
):
    """Screen locker that requires workout logging to unlock."""

    def __init__(
        self,
        *,
        demo_mode: bool = True,
        verify_only: bool = False,
    ) -> None:
        """Initialize screen locker with optional demo mode."""
        _assert_not_under_pytest()
        script_dir = Path(__file__).resolve().parent
        self.log_file = script_dir / "workout_log.json"
        self.verify_only = verify_only
        self.workout_data: dict[str, str] = {}
        self._relaxed_day_mode: bool = False
        self._check_early_exits(verify_only=verify_only)
        self.root = GateRoot()
        self.root.on_callback_error = self.on_callback_error
        title_suffix = (
            " [VERIFY]" if verify_only else (" [DEMO MODE]" if demo_mode else "")
        )
        self.root.title("Workout Locker" + title_suffix)
        self.demo_mode = demo_mode
        self.lockout_time = 10 if demo_mode else 1800
        self._lock: LockWindow | None = None
        if verify_only:
            self._setup_verify_window()
        elif self._relaxed_day_mode:
            self._setup_relaxed_day_window()
        else:
            config = LockConfig(
                mode="hard",
                grab="local" if demo_mode else "global",
                disable_vt=not demo_mode,
            )
            self._lock = LockWindow(self.root, config, hooks=self)
            self._lock.setup()
            if demo_mode:
                self._setup_demo_close_button()
        self.container = tk.Frame(self.root, bg="#1a1a1a")
        self.container.place(relx=0.5, rely=0.5, anchor="center")
        self._phone_future: Future[tuple[str, str]] | None = None
        self._runnerup_future: Future[tuple[str, str]] | None = None
        self._runnerup_on_failure: Callable[[], None] | None = None
        if verify_only:
            self._start_verify_workout_check()
        elif self._relaxed_day_mode:
            self._start_relaxed_day_flow()
        else:
            self._start_phone_check()
            # Always set on this branch; guard only for mypy (can't narrow
            # across two separate if/elif/else statements).
            if self._lock is not None:  # pragma: no branch
                self._lock.grab_input()

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

    def _apply_weekly_shutdown_bonus(self) -> None:
        """Layer this week's earned shutdown bonus back on top of the fresh base."""
        bonus = weekly_shutdown_bonus_hours(EXTRA_BENEFITS_FILE)
        if bonus > 0 and self._adjust_shutdown_time_by(bonus):
            _logger.info("Weekly bonus: +%dh shutdown time this week.", bonus)

    def unlock_screen(self) -> None:
        """Apply workout credit and display success message."""
        credit = self._apply_workout_credit()

        self.clear_container()
        self._label("Great job! 💪", font_size=48, color="#00ff00", pady=30)
        if credit.shutdown_adjusted:
            self._text(
                "Shutdown time +2h later! 🎁",
                font_size=24,
                color="#ffaa00",
            )
        if credit.extra_bonus_delta > 0:
            extra_n = credit.weekly_count - WEEKLY_WORKOUT_MINIMUM
            self._text(
                f"Extra workout #{extra_n}! +{credit.extra_bonus_delta}h tonight",
                font_size=20,
                color="#ffaa00",
            )
        if credit.new_debt is not None:
            self._text(
                f"Workout debt: {credit.new_debt}",
                font_size=20,
                color="#ffaa00" if credit.new_debt > 0 else "#888888",
            )
        streak = current_streak(EXTRA_BENEFITS_FILE)
        if streak >= 1:
            self._text(
                f"🔥 {streak}-week streak (5+ workouts each)",
                font_size=14,
                color="#888888",
            )
        self._text("Screen Unlocked!", font_size=36, pady=20)
        if self.workout_data.get("type") in (
            "phone_verified",
            "runnerup_verified",
            "manual_workout",
        ):
            self.root.after(
                1500,
                lambda: self._show_commitment_prompt(on_done=self.close),
            )
        else:
            self.root.after(1500, self.close)

    def close(self) -> None:
        """Close the application and exit."""
        if self._lock is not None:
            self._lock.close()
        else:
            self.root.destroy()
        sys.exit(0)

    def run(self) -> None:
        """Start the Tkinter main event loop."""
        if self._lock is not None:
            self._lock.run()
        else:
            self.root.mainloop()


if __name__ == "__main__":
    if "--status" in sys.argv:
        from screen_locker._status import run_status

        # Bypass __init__ (no UI) — only log_file and workout_data are needed.
        _sl = object.__new__(ScreenLocker)
        _sl.log_file = Path(__file__).resolve().parent / "workout_log.json"
        _sl.workout_data = {}
        run_status(_sl)

    demo_mode = True
    verify_only = "--verify-workout" in sys.argv

    if "--production" in sys.argv:
        demo_mode = False

    locker = ScreenLocker(
        demo_mode=demo_mode,
        verify_only=verify_only,
    )
    locker.run()
