"""UI flow methods mixin for the screen locker."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from python_pkg.screen_locker._constants import (
    PHONE_PENALTY_DELAY_DEMO,
    PHONE_PENALTY_DELAY_PRODUCTION,
    SICK_LOCKOUT_SECONDS,
)


class UIFlowsMixin:
    """Mixin providing UI flow logic for the screen locker."""

    def ask_workout_done(self) -> None:
        """Display the initial workout question dialog."""
        self.clear_container()
        self._label("Did you work out today?", pady=30)
        frame = self._button_row()
        self._button(
            frame,
            "YES",
            bg="#00aa00",
            command=self.ask_workout_type,
        ).pack(side="left", padx=20)
        self._button(
            frame,
            "NO",
            bg="#aa0000",
            command=self.ask_if_sick,
        ).pack(side="left", padx=20)

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
            self.clear_container()
            self._label("No Workout Found", font_size=36, color="#ff4444", pady=20)
            self._text(
                f"\u274c {message}\n\n"
                "StrongLifts shows no workout today.\n"
                "Go do your workout first!",
                color="#ffaa00",
            )
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
        else:
            # no_phone or error — penalty timer, then proceed to logging form
            self._show_phone_penalty(message, on_done=self.ask_workout_done)

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
            self.ask_workout_done()

    # ------------------------------------------------------------------
    # Phone penalty
    # ------------------------------------------------------------------

    def _attempt_unlock(self) -> None:
        """Unlock screen after workout form submission."""
        self.unlock_screen()

    def _show_phone_penalty(
        self, message: str, *, on_done: Callable[[], None] | None = None
    ) -> None:
        """Show penalty countdown when phone verification is unavailable."""
        self.clear_container()
        self._phone_penalty_done_fn: Callable[[], None] = (
            on_done if on_done is not None else self.unlock_screen
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
    # Submit timer and entry checking
    # ------------------------------------------------------------------

    def _tick_submit_timer(self) -> None:
        """Decrement submit timer and schedule next tick."""
        self.timer_label.config(
            text=f"Submit available in {self.submit_unlock_time} seconds...",
        )
        self.submit_unlock_time -= 1
        self.root.after(1000, self.update_submit_timer)

    def _try_enable_submit(self) -> None:
        """Enable submit button if all entries are filled."""
        all_filled = all(entry.get().strip() for entry in self.entries_to_check)
        if all_filled:
            self.submit_btn.config(
                text="SUBMIT",
                state="normal",
                bg="#00aa00",
                command=self.submit_command,
            )
            self.timer_label.config(text="You can now submit!")
        else:
            self.timer_label.config(text="Fill all fields to enable submit")
            self.root.after(1000, self.check_entries_filled)

    def update_submit_timer(self) -> None:
        """Update countdown timer and check if submit can be enabled."""
        with contextlib.suppress(tk.TclError):
            if self.submit_unlock_time > 0:
                self._tick_submit_timer()
            else:
                self._try_enable_submit()

    def check_entries_filled(self) -> None:
        """Continuously check if entries are filled after timer expires."""
        with contextlib.suppress(tk.TclError):
            self._try_enable_submit()
