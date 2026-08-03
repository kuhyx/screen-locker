"""Verify-workout and relaxed-day UI flow methods mixin."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # pylint: disable=no-name-in-module

from screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM,
    count_weekly_workouts,
)


class UIFlowsRelaxedMixin:
    """Mixin providing verify-workout and relaxed-day UI flow logic."""

    # ------------------------------------------------------------------
    # Verify-workout flow (post-sick-day)
    # ------------------------------------------------------------------

    def _start_verify_workout_check(self) -> None:
        """Start phone check for post-sick-day workout verification."""
        self.clear_container()
        self._label(
            "Verifying Workout",
            role="display",
            color=self._colors.warning,
            pad="lg",
        )
        self._text(
            "Checking phone for today's workout...",
            role="body",
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
                "✓ Workout Verified!",
                role="display",
                scale=1.3,
                color=self._colors.success,
                pad="lg",
            )
            self._text(message, role="subtitle", color=self._colors.success)
            if adjusted:
                self._text(
                    "Shutdown time moved later!",
                    role="subtitle",
                    color=self._colors.warning,
                )
            self.root.after(2000, self.close)
        else:
            self._show_verify_retry(message)

    def _show_verify_retry(self, message: str) -> None:
        """Show retry/close buttons when workout not found in verify mode."""
        self.clear_container()
        self._label(
            "Workout Not Found",
            role="display",
            color=self._colors.danger,
            pad="md",
        )
        self._text(message, color=self._colors.warning)
        frame = self._button_row()
        self._button(
            frame,
            "TRY AGAIN",
            bg=self._colors.accent,
            command=self._start_verify_workout_check,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            frame,
            "Close",
            bg=self._colors.field_bg,
            command=self.close,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))

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
            color=self._colors.warning,
            pad="md",
        )
        self._text(
            f"Weekly workouts: {count} / {WEEKLY_WORKOUT_MINIMUM}\n"
            "No penalty for skipping today.",
            role="subtitle",
            color=self._colors.muted,
            pad="sm",
        )
        frame = self._button_row()
        self._button(
            frame,
            "Skip — No Penalty",
            bg=self._colors.success,
            command=self.close,
            width=18,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            frame,
            "Log Stronglift Workout",
            bg=self._colors.accent,
            command=self._start_relaxed_phone_check,
            width=20,
        ).pack(side="left", padx=self._colors.space("sm"))

    def _start_relaxed_phone_check(self) -> None:
        """Run Stronglift check in relaxed mode (no screen grab, no sick option)."""
        self.clear_container()
        self._label(
            "Checking phone...", role="display", color=self._colors.warning, pad="lg"
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
        On failure shows retry and close — no sick option since skipping is free.
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
            "No Workout Found", role="display", color=self._colors.danger, pad="md"
        )
        self._text(f"❌ {message}\n\nReason: {status}", color=self._colors.warning)
        frame = self._button_row()
        self._button(
            frame,
            "TRY AGAIN",
            bg=self._colors.accent,
            command=self._start_relaxed_phone_check,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            frame,
            "Close (Skip)",
            bg=self._colors.success,
            command=self.close,
            width=14,
        ).pack(side="left", padx=self._colors.space("sm"))
