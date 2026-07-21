"""UI flow methods mixin for the screen locker."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # pylint: disable=no-name-in-module
from typing import TYPE_CHECKING

from screen_locker import _manual_workout, _sick_tracker
from screen_locker._constants import (
    NO_PHONE_EXTRA_LOCKOUT_SECONDS,
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class UIFlowsMixin:
    """Mixin providing UI flow logic for the screen locker."""

    def _start_phone_check(self) -> None:
        """Check phone for today's workout immediately at startup."""
        self.clear_container()
        self._label(
            "Checking phone...", font_size=36, color=self._colors.warning, pady=30
        )
        self._text("Looking for today's workout in StrongLifts...", font_size=18)
        executor = ThreadPoolExecutor(max_workers=1)
        self._phone_future = executor.submit(self._verify_phone_workout)
        executor.shutdown(wait=False)
        self._poll_phone_check()

    def _poll_phone_check(self) -> None:
        """Poll background phone check and route to result handler when done."""
        if self._phone_future is not None and self._phone_future.done():
            status, message = self._phone_future.result()
            self._handle_startup_phone_result(status, message)
        else:
            self.root.after(500, self._poll_phone_check)

    def _show_retry_and_sick(self, message: str) -> None:
        """Show TRY AGAIN and (if budget allows) I'm sick after a failed check."""
        self.clear_container()
        self._label(
            "No Workout Found", font_size=36, color=self._colors.danger, pady=20
        )
        self._text(message, color=self._colors.warning)
        history = _sick_tracker.load_history()
        self._text(_sick_tracker.budget_summary(history), color=self._colors.muted)
        self._text(
            _manual_workout.budget_summary(self.log_file), color=self._colors.muted
        )
        frame = self._button_row()
        self._button(
            frame,
            "TRY AGAIN",
            bg=self._colors.accent,
            command=self._start_phone_check,
            width=12,
        ).pack(side="left", padx=10)
        if _sick_tracker.is_budget_exhausted(history):
            self._text(
                "Sick budget exhausted. No 'I'm sick' option available.",
                color=self._colors.danger,
            )
        else:
            self._button(
                frame,
                "I'm sick",
                bg=self._colors.warning,
                command=self.ask_if_sick,
                width=12,
            ).pack(side="left", padx=10)
        if _manual_workout.is_budget_exhausted(self.log_file):
            self._text(
                "Manual-workout budget exhausted. No manual-log option available.",
                color=self._colors.danger,
            )
        else:
            self._button(
                frame,
                "Log Manual Workout",
                bg=self._colors.accent,
                command=self._show_manual_workout_form,
                width=16,
            ).pack(side="left", padx=10)

    def _on_manual_workout_saved(self, entry: dict) -> None:
        """Show confirmation and unlock after a manual-workout entry is built."""
        self.workout_data = entry
        self.clear_container()
        self._label(
            "✓ Manual Workout Logged!",
            font_size=42,
            color=self._colors.success,
            pady=30,
        )
        self._text(entry.get("source", ""), font_size=20, color=self._colors.success)
        self._text("Unlocking...", font_size=18, color=self._colors.muted)
        unlock_delay = 1500 if self.demo_mode else 2000
        self.root.after(unlock_delay, self.unlock_screen)

    def _on_manual_workout_cancelled(self) -> None:
        """Return to the retry screen when the manual-workout form is cancelled."""
        self._start_phone_check()

    def _handle_startup_phone_result(self, status: str, message: str) -> None:
        """Route to appropriate screen based on startup phone check result."""
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            self.clear_container()
            self._label(
                "✓ Workout Verified!",
                font_size=42,
                color=self._colors.success,
                pady=30,
            )
            self._text(message, font_size=20, color=self._colors.success)
            self._text("Unlocking...", font_size=18, color=self._colors.muted)
            unlock_delay = 1500 if self.demo_mode else 2000
            self.root.after(unlock_delay, self.unlock_screen)
        elif status == "too_short":
            self._show_retry_and_sick(
                f"❌ {message}\n\n"
                "Your workout was too short!\n"
                "Actually do the full workout, don't just\n"
                "spam through the exercises.",
            )
        elif status == "clock_tampered":
            self._show_retry_and_sick(
                f"❌ {message}\n\n"
                "System clock appears to be manipulated.\n"
                "Fix your system time and try again.",
            )
        elif status in ("stale", "no_exercises", "not_verified"):
            # Try RunnerUp before showing failure — user may have run instead of lifted.
            self._start_runnerup_fallback(
                lambda: self._show_retry_and_sick(
                    f"❌ {message}\n\n"
                    "Neither StrongLifts nor RunnerUp found a workout today.\n"
                    "Go do your workout first!",
                )
            )
        else:
            # no_phone or error — try RunnerUp first, then penalty timer.
            self._start_runnerup_fallback(lambda: self._show_phone_penalty(message))

    def _start_runnerup_fallback(self, on_failure: Callable[[], None]) -> None:
        """Check RunnerUp as fallback after phone check fails.

        Shows a waiting screen, runs the check in a background thread, then
        either unlocks (run verified) or calls ``on_failure``.
        """
        self.clear_container()
        self._label(
            "Checking RunnerUp...", font_size=36, color=self._colors.warning, pady=30
        )
        self._text("Looking for today's run in RunnerUp...", font_size=18)
        executor = ThreadPoolExecutor(max_workers=1)
        self._runnerup_future = executor.submit(self._verify_runnerup_workout)
        executor.shutdown(wait=False)
        self._runnerup_on_failure = on_failure
        self._poll_runnerup_fallback()

    def _poll_runnerup_fallback(self) -> None:
        """Poll the RunnerUp background check and route to result handler."""
        if self._runnerup_future is not None and self._runnerup_future.done():
            status, message = self._runnerup_future.result()
            if status == "verified":
                self.workout_data["type"] = "runnerup_verified"
                self.workout_data["source"] = message
                self.clear_container()
                self._label(
                    "✓ Run Verified!",
                    font_size=42,
                    color=self._colors.success,
                    pady=30,
                )
                self._text(message, font_size=20, color=self._colors.success)
                self._text("Unlocking...", font_size=18, color=self._colors.muted)
                unlock_delay = 1500 if self.demo_mode else 2000
                self.root.after(unlock_delay, self.unlock_screen)
            else:
                self._runnerup_on_failure()
        else:
            self.root.after(500, self._poll_runnerup_fallback)

    def ask_if_sick(self) -> None:
        """Display the structured sick-day justification dialog."""
        self._show_sick_justification()

    def _get_sick_day_status(self) -> tuple[str, str]:
        """Determine sick day status text and color."""
        if self._sick_mode_used_today():
            return "Shutdown time already adjusted today", self._colors.warning
        if self._adjust_shutdown_time_earlier():
            return (
                "Shutdown time moved 1.5 hours earlier ✓\n(Will revert tomorrow)"
            ), self._colors.success
        return (
            "Could not adjust shutdown time (check permissions)",
            self._colors.danger,
        )

    def _proceed_to_sick_countdown(self) -> None:
        """Start the (escalated) sick day countdown after justification."""
        history = getattr(
            self,
            "_sick_history_cache",
            None,
        )
        if history is None:
            history = _sick_tracker.load_history()
            self._sick_history_cache = history
        countdown = _sick_tracker.compute_lockout_seconds(history)
        self.clear_container()
        status_text, status_color = self._get_sick_day_status()
        self._show_sick_day_ui(status_text, status_color, countdown)
        self.sick_remaining_time = countdown
        self._update_sick_countdown()

    def _show_sick_day_ui(
        self,
        status_text: str,
        status_color: str,
        countdown: int,
    ) -> None:
        """Display sick day UI labels and countdown."""
        self._label("Sick Day Mode", color=self._colors.warning, pady=20)
        self._text(status_text, color=status_color)
        minutes = countdown // 60
        self._text(
            f"Please wait ~{minutes} min before unlocking...",
            font_size=24,
            pady=20,
        )
        self.sick_countdown_label = self._label(
            str(countdown),
            font_size=80,
            pady=30,
        )

    def _update_sick_countdown(self) -> None:
        """Update the sick day countdown timer."""
        if self.sick_remaining_time > 0:
            self.sick_countdown_label.config(text=str(self.sick_remaining_time))
            self.sick_remaining_time -= 1
            self.root.after(1000, self._update_sick_countdown)
        else:
            self._finalize_sick_day()

    def _finalize_sick_day(self) -> None:
        """Persist sick-day history and unlock the screen."""
        history = getattr(self, "_sick_history_cache", None)
        if history is None:
            history = _sick_tracker.load_history()
        if _sick_tracker.had_commitment_for_today(history):
            _sick_tracker.mark_commitment_broken(history)
            self.workout_data["broke_commitment"] = "true"
        new_debt = _sick_tracker.add_sick_day(history)
        _sick_tracker.save_history(history)
        self.workout_data["type"] = "sick_day"
        self.workout_data["note"] = "Sick day - shutdown moved earlier"
        self.workout_data["debt"] = str(new_debt)
        self.unlock_screen()

    # ------------------------------------------------------------------
    # Lockout flow
    # ------------------------------------------------------------------

    def lockout(self) -> None:
        """Display lockout screen with countdown timer."""
        self.clear_container()
        self.lockout_label = self._label(
            f"Go work out!\nLocked for {self.lockout_time} seconds",
            font_size=48,
            color=self._colors.danger,
            pady=30,
        )
        self.countdown_label = self._label(
            str(self.lockout_time),
            font_size=120,
            pady=30,
        )
        self.remaining_time = self.lockout_time
        self.update_lockout_countdown()

    def update_lockout_countdown(self) -> None:
        """Update the lockout countdown timer display."""
        if self.remaining_time > 0:
            self.countdown_label.config(text=str(self.remaining_time))
            self.remaining_time -= 1
            self.root.after(1000, self.update_lockout_countdown)
        else:
            self._start_phone_check()

    # ------------------------------------------------------------------
    # Phone penalty
    # ------------------------------------------------------------------

    def _show_phone_penalty(
        self, message: str, *, on_done: Callable[[], None] | None = None
    ) -> None:
        """Show penalty countdown when phone verification is unavailable."""
        self.clear_container()
        self._phone_penalty_done_fn: Callable[[], None] = (
            on_done
            if on_done is not None
            else lambda: self._show_retry_and_sick(message)
        )
        base_delay = (
            PHONE_PENALTY_DELAY_DEMO
            if self.demo_mode
            else PHONE_PENALTY_DELAY_PRODUCTION
        )
        # Disconnecting the phone shouldn't be a fast path into sick mode.
        delay = (
            base_delay
            if self.demo_mode
            else base_delay + NO_PHONE_EXTRA_LOCKOUT_SECONDS
        )
        self._label(
            "Cannot Verify Workout",
            font_size=36,
            color=self._colors.warning,
            pady=20,
        )
        self._text(message, color=self._colors.warning)
        self._text(
            "Connect phone via ADB to skip this wait,\n"
            "or wait for the penalty timer.\n\n"
            "Note: Phone must be rooted and StrongLifts installed.",
            font_size=18,
        )
        self.phone_penalty_remaining = delay
        self.phone_penalty_label = self._label(
            str(delay),
            font_size=80,
            pady=20,
        )
        self._update_phone_penalty()

    def _update_phone_penalty(self) -> None:
        """Update phone penalty countdown."""
        if self.phone_penalty_remaining > 0:
            self.phone_penalty_label.config(
                text=str(self.phone_penalty_remaining),
            )
            self.phone_penalty_remaining -= 1
            self.root.after(1000, self._update_phone_penalty)
        else:
            self._phone_penalty_done_fn()
