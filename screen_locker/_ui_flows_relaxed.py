"""Relaxed-day (Tue/Wed/Thu) UI flow methods mixin."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # pylint: disable=no-name-in-module

from screen_locker._weekly_check import (
    RELAXED_DAY_SKIP_TYPE,
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
)


class UIFlowsRelaxedMixin:
    """Mixin providing the relaxed-day UI flow logic."""

    # ------------------------------------------------------------------
    # Relaxed-day flow (Tue/Wed/Thu — optional, no penalty for skipping)
    # ------------------------------------------------------------------

    def _start_relaxed_day_flow(self) -> None:
        """Show optional workout prompt for relaxed days (Tue-Thu).

        The screen is not locked — the user can skip freely or voluntarily
        import a Stronglift workout that counts toward the weekly minimum.
        """
        count = count_weekly_workouts(self.log_file)
        self.clear_container()
        self._label(
            "Optional Day (Tue / Wed / Thu)",
            role="title",
            color=self._colors.palette.warning,
            pad="md",
        )
        self._text(
            f"Weekly workouts: {count} / {WEEKLY_WORKOUT_MINIMUM}\n"
            "No penalty for skipping today.",
            role="subtitle",
            color=self._colors.palette.muted,
            pad="sm",
        )
        frame = self._button_row()
        self._button(
            frame,
            "Skip — No Penalty",
            bg=self._colors.palette.success,
            command=self._skip_relaxed_day,
            width=18,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            frame,
            "Log Stronglift Workout",
            bg=self._colors.palette.accent,
            command=self._start_relaxed_phone_check,
            width=20,
        ).pack(side="left", padx=self._colors.space("sm"))
        # Skipping is free here, but a sick day is more than a skip: it
        # stands every gate down and lifts tonight's shutdown to 20:00.
        self._sick_button(frame)

    def _skip_relaxed_day(self) -> None:
        """Dismiss today's relaxed-day prompt for the rest of the calendar day.

        Without a persisted marker here, the recurring 30-minute
        ``workout-locker.timer`` re-derives ``relaxed_day`` from scratch every
        tick and rebuilds this same prompt, since the underlying date check
        has no memory of its own of an earlier same-day dismissal.
        """
        self.workout_data = {"type": RELAXED_DAY_SKIP_TYPE}
        self.save_workout_log()
        self.close()

    def _start_relaxed_phone_check(self) -> None:
        """Run Stronglift check in relaxed mode (no screen grab)."""
        self.clear_container()
        self._label(
            "Checking phone...",
            role="display",
            color=self._colors.palette.warning,
            pad="lg",
        )
        self._text("Looking for today's workout in StrongLifts...", role="body")
        executor = ThreadPoolExecutor(max_workers=1)
        self._phone_future = executor.submit(self._verify_phone_workout)
        executor.shutdown(wait=False)
        self._poll_relaxed_phone_check()

    def _poll_relaxed_phone_check(self) -> None:
        """Poll background phone check in relaxed-day mode."""
        if self._phone_future is not None and self._phone_future.done():
            status, message = self._phone_future.result()
            self._handle_relaxed_phone_result(status, message)
        else:
            self.root.after(500, self._poll_relaxed_phone_check)

    def _handle_relaxed_phone_result(self, status: str, message: str) -> None:
        """Route phone check result in relaxed-day mode.

        On success saves the workout (counts toward weekly total) then closes.
        On failure shows retry, I'm sick and close.
        """
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            unlock_delay = 1500 if self.demo_mode else 2000
            self.root.after(unlock_delay, self.unlock_screen)
        else:
            self._show_relaxed_retry(message, status)

    def _show_relaxed_retry(self, message: str, status: str) -> None:
        """Show retry and skip-close when workout not found in relaxed mode."""
        self.clear_container()
        self._label(
            "No Workout Found",
            role="display",
            color=self._colors.palette.danger,
            pad="md",
        )
        self._text(
            f"❌ {message}\n\nReason: {status}", color=self._colors.palette.warning
        )
        frame = self._button_row()
        self._button(
            frame,
            "TRY AGAIN",
            bg=self._colors.palette.accent,
            command=self._start_relaxed_phone_check,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._sick_button(frame)
        self._button(
            frame,
            "Close (Skip)",
            bg=self._colors.palette.success,
            command=self.close,
            width=14,
        ).pack(side="left", padx=self._colors.space("sm"))
