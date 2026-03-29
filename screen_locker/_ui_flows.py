"""UI flow methods mixin for the screen locker."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from python_pkg.screen_locker._constants import (
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    SICK_LOCKOUT_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class UIFlowsMixin:
    """Mixin providing UI flow logic for the screen locker."""

    def _start_phone_check(self) -> None:
        """Check phone for today's workout immediately at startup."""
        self.clear_container()
        self._label("Checking phone...", font_size=36, color="#ffaa00", pady=30)
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
        """Show TRY AGAIN and I'm sick buttons after a failed phone check."""
        self.clear_container()
        self._label("No Workout Found", font_size=36, color="#ff4444", pady=20)
        self._text(message, color="#ffaa00")
        frame = self._button_row()
        self._button(
            frame,
            "TRY AGAIN",
            bg="#0066cc",
            command=self._start_phone_check,
            width=12,
        ).pack(side="left", padx=10)
        self._button(
            frame,
            "I'm sick",
            bg="#cc6600",
            command=self.ask_if_sick,
            width=12,
        ).pack(side="left", padx=10)

    def _handle_startup_phone_result(self, status: str, message: str) -> None:
        """Route to appropriate screen based on startup phone check result."""
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            self.clear_container()
            self._label(
                "\u2713 Workout Verified!", font_size=42, color="#00cc44", pady=30
            )
            self._text(message, font_size=20, color="#aaffaa")
            self._text("Unlocking...", font_size=18, color="#888888")
            unlock_delay = 1500 if self.demo_mode else 2000
            self.root.after(unlock_delay, self.unlock_screen)
        elif status == "not_verified":
            self._show_retry_and_sick(
                f"\u274c {message}\n\n"
                "StrongLifts shows no workout today.\n"
                "Go do your workout first!",
            )
        else:
            # no_phone or error — penalty timer, then retry+sick screen
            self._show_phone_penalty(message)

    def ask_if_sick(self) -> None:
        """Display sick day question dialog."""
        self.clear_container()
        self._label("Are you sick?", pady=30)
        self._text(
            "If yes, shutdown time will be moved 1.5 hours earlier",
            color="#ffaa00",
        )
        self._sick_question_buttons()

    def _sick_question_buttons(self) -> None:
        """Create the sick day yes/no buttons."""
        frame = self._button_row()
        self._button(
            frame,
            "YES (sick)",
            bg="#cc6600",
            command=self.handle_sick_day,
            width=12,
        ).pack(side="left", padx=20)
        self._button(
            frame,
            "NO",
            bg="#aa0000",
            command=self.lockout,
            width=12,
        ).pack(side="left", padx=20)

    def _get_sick_day_status(self) -> tuple[str, str]:
        """Determine sick day status text and color."""
        if self._sick_mode_used_today():
            return "Shutdown time already adjusted today", "#ffaa00"
        if self._adjust_shutdown_time_earlier():
            return (
                "Shutdown time moved 1.5 hours earlier \u2713\n(Will revert tomorrow)"
            ), "#00aa00"
        return "Could not adjust shutdown time (check permissions)", "#ff4444"

    def handle_sick_day(self) -> None:
        """Handle sick day: adjust shutdown time and start 2-minute wait."""
        self.clear_container()
        status_text, status_color = self._get_sick_day_status()
        self._show_sick_day_ui(status_text, status_color)
        self.sick_remaining_time = SICK_LOCKOUT_SECONDS
        self._update_sick_countdown()

    def _show_sick_day_ui(self, status_text: str, status_color: str) -> None:
        """Display sick day UI labels and countdown."""
        self._label("Sick Day Mode", color="#cc6600", pady=20)
        self._text(status_text, color=status_color)
        self._text(
            "Please wait 2 minutes before unlocking...",
            font_size=24,
            pady=20,
        )
        self.sick_countdown_label = self._label(
            str(SICK_LOCKOUT_SECONDS),
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
            # Record sick day and unlock
            self.workout_data["type"] = "sick_day"
            self.workout_data["note"] = "Sick day - shutdown moved earlier"
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
            color="#ff4444",
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
        delay = (
            PHONE_PENALTY_DELAY_DEMO
            if self.demo_mode
            else PHONE_PENALTY_DELAY_PRODUCTION
        )
        self._label(
            "Cannot Verify Workout",
            font_size=36,
            color="#ff8800",
            pady=20,
        )
        self._text(message, color="#ffaa00")
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

    # ------------------------------------------------------------------
    # Verify-workout flow (post-sick-day)
    # ------------------------------------------------------------------

    def _start_verify_workout_check(self) -> None:
        """Start phone check for post-sick-day workout verification."""
        self.clear_container()
        self._label(
            "Verifying Workout",
            font_size=36,
            color="#ffaa00",
            pady=30,
        )
        self._text(
            "Checking phone for today's workout...",
            font_size=18,
        )
        executor = ThreadPoolExecutor(max_workers=1)
        self._phone_future = executor.submit(self._verify_phone_workout)
        executor.shutdown(wait=False)
        self._poll_verify_workout_check()

    def _poll_verify_workout_check(self) -> None:
        """Poll background phone check for verify-workout mode."""
        if self._phone_future is not None and self._phone_future.done():
            status, message = self._phone_future.result()
            self._handle_verify_workout_result(status, message)
        else:
            self.root.after(500, self._poll_verify_workout_check)

    def _handle_verify_workout_result(
        self,
        status: str,
        message: str,
    ) -> None:
        """Route phone check result in verify-workout mode."""
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            self.workout_data["after_sick_day"] = "true"
            adjusted = self._adjust_shutdown_time_later()
            self.save_workout_log()
            self.clear_container()
            self._label(
                "\u2713 Workout Verified!",
                font_size=42,
                color="#00cc44",
                pady=30,
            )
            self._text(message, font_size=20, color="#aaffaa")
            if adjusted:
                self._text(
                    "Shutdown time moved later!",
                    font_size=20,
                    color="#ffaa00",
                )
            self.root.after(2000, self.close)
        else:
            self._show_verify_retry(message)

    def _show_verify_retry(self, message: str) -> None:
        """Show retry/close buttons when workout not found in verify mode."""
        self.clear_container()
        self._label(
            "Workout Not Found",
            font_size=36,
            color="#ff4444",
            pady=20,
        )
        self._text(message, color="#ffaa00")
        frame = self._button_row()
        self._button(
            frame,
            "TRY AGAIN",
            bg="#0066cc",
            command=self._start_verify_workout_check,
            width=12,
        ).pack(side="left", padx=10)
        self._button(
            frame,
            "Close",
            bg="#aa0000",
            command=self.close,
            width=12,
        ).pack(side="left", padx=10)
