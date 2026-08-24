"""UI flow methods mixin for the screen locker."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # pylint: disable=no-name-in-module
from typing import TYPE_CHECKING

from screen_locker import _manual_workout, _sick_tracker
from screen_locker._source_health import collect_source_findings, explain_findings
from screen_locker._ui_flows_lockout import LockoutFlowMixin
from screen_locker._ui_flows_sick import SickDayFlowMixin

if TYPE_CHECKING:
    from collections.abc import Callable


class UIFlowsMixin(SickDayFlowMixin, LockoutFlowMixin):
    """Mixin providing UI flow logic for the screen locker.

    The sick-day and lockout/penalty flows live in sibling modules and are
    composed in here, so ``ScreenLocker``'s own mixin list stays as it was.
    """

    def paint_phone_check(self) -> None:
        """Paint the "checking phone" screen, without starting the check.

        Split from :meth:`_start_phone_check` so the fit check
        (``scripts/verify_screen_fits.py``) can measure this screen without
        starting a background thread that talks to a phone over adb.
        """
        self.clear_container()
        self._label(
            "Checking phone...", role="display", color=self._colors.warning, pad="lg"
        )
        self._text("Looking for today's workout in StrongLifts...", role="body")

    def _start_phone_check(self) -> None:
        """Check phone for today's workout immediately at startup."""
        self.paint_phone_check()
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
            "No Workout Found", role="display", color=self._colors.danger, pad="md"
        )
        self._text(message, color=self._colors.warning)
        # Never accuse the user of skipping a workout the machine simply could
        # not see. On 2026-08-24 this screen said "No Workout Found" after a
        # 1h57m session, because Firebase was unreadable and the GitHub mirror
        # had been stale for nine days -- neither of which was shown here.
        diagnosis = explain_findings(collect_source_findings())
        if diagnosis:
            self._text(diagnosis, color=self._colors.muted)
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
        ).pack(side="left", padx=self._colors.space("sm"))
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
            ).pack(side="left", padx=self._colors.space("sm"))
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
            ).pack(side="left", padx=self._colors.space("sm"))

    def _on_manual_workout_saved(self, entry: dict) -> None:
        """Show confirmation and unlock after a manual-workout entry is built."""
        self.workout_data = entry
        self.clear_container()
        self._label(
            "✓ Manual Workout Logged!",
            role="display",
            scale=1.3,
            color=self._colors.success,
            pad="lg",
        )
        self._text(entry.get("source", ""), role="subtitle", color=self._colors.success)
        self._text("Unlocking...", role="body", color=self._colors.muted)
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
                role="display",
                scale=1.3,
                color=self._colors.success,
                pad="lg",
            )
            self._text(message, role="subtitle", color=self._colors.success)
            self._text("Unlocking...", role="body", color=self._colors.muted)
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
            "Checking RunnerUp...", role="display", color=self._colors.warning, pad="lg"
        )
        self._text("Looking for today's run in RunnerUp...", role="body")
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
                    role="display",
                    scale=1.3,
                    color=self._colors.success,
                    pad="lg",
                )
                self._text(message, role="subtitle", color=self._colors.success)
                self._text("Unlocking...", role="body", color=self._colors.muted)
                unlock_delay = 1500 if self.demo_mode else 2000
                self.root.after(unlock_delay, self.unlock_screen)
            else:
                self._runnerup_on_failure()
        else:
            self.root.after(500, self._poll_runnerup_fallback)
