"""UI flow methods mixin for the screen locker.

textgate: every screen here is glyphs (``_glyphs``) plus numbers, with the
palette colour as the second channel. The sentences these screens used to
paint ("No Workout Found", the verifier's reason, the sync diagnosis) go to
the log at warning instead, so the reason is never lost, only unpainted.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import TYPE_CHECKING

from screen_locker import _glyphs as g
from screen_locker import _manual_workout
from screen_locker._source_health import collect_source_findings, explain_findings
from screen_locker._ui_flows_lockout import LockoutFlowMixin
from screen_locker._ui_flows_sick import SickDayFlowMixin
from screen_locker._ui_flows_sick_panel import SickPanelFlowMixin

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


class UIFlowsMixin(SickDayFlowMixin, SickPanelFlowMixin, LockoutFlowMixin):
    """Mixin providing UI flow logic for the screen locker.

    The sick-day and lockout/penalty flows live in sibling modules and are
    composed in here, so ``ScreenLocker``'s own mixin list stays as it was.
    """

    def paint_phone_check(self) -> None:
        """Paint the "checking phone" screen, without starting the check.

        Split from :meth:`_start_phone_check` so the fit check
        (``scripts/verify_screen_fits.py``) can measure this screen without
        starting a background thread that talks to a phone over adb.
        Was "Checking phone..." / "Looking for today's workout in StrongLifts".
        """
        self.clear_container()
        self._label(
            f"{g.PHONE} {g.LIFT}",
            role="display",
            color=self._colors.palette.warning,
            pad="lg",
        )
        self._text(g.WAIT, role="display", color=self._colors.palette.muted)

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

    def _show_retry_and_sick(self, message: str, *, status: str = "") -> None:
        """Show retry, I'm sick and (budget allowing) the manual log.

        Was "No Workout Found" over *message*. The screen now shows the
        failure glyph for *status*; *message* goes to the log.
        """
        _logger.warning("No workout accepted (%s): %s", status or "?", message)
        self.clear_container()
        self._label(
            f"{g.LIFT} {g.FAIL}",
            role="display",
            color=self._colors.palette.danger,
            pad="md",
        )
        if status:
            self._text(
                g.status_glyph(status),
                role="display",
                color=self._colors.palette.warning,
            )
        # Never accuse the user of skipping a workout the machine simply could
        # not see. On 2026-08-24 this screen said "No Workout Found" after a
        # 1h57m session, because Firebase was unreadable and the GitHub mirror
        # had been stale for nine days -- neither of which was shown here.
        # Now a sync-fault glyph, one per finding; the prose is logged.
        findings = collect_source_findings()
        if findings:
            _logger.warning("%s", explain_findings(findings))
            self._text(
                f"{g.SYNC}{g.FAIL} " * len(findings),
                role="title",
                color=self._colors.palette.warning,
            )
        self._text(
            _manual_workout.budget_summary(self.log_file),
            color=self._colors.palette.muted,
        )
        frame = self._button_row()
        self._button(
            frame,
            g.RETRY,
            bg=self._colors.palette.accent,
            command=self._start_phone_check,
            width=4,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._sick_button(frame)
        if self._mw_budget_closed():
            # Was "Manual-workout budget exhausted. No manual-log option".
            self._text(f"{g.FORM} {g.CLOSE}", color=self._colors.palette.danger)
        else:
            self._button(
                frame,
                g.FORM,
                bg=self._colors.palette.accent,
                command=self._show_manual_workout_form,
                width=4,
            ).pack(side="left", padx=self._colors.space("sm"))

    def _paint_accepted(self, glyph: str) -> None:
        """Paint "accepted, unlocking" and schedule the unlock.

        Was "✓ Workout Verified!" / "✓ Run Verified!" / "✓ Manual Workout
        Logged!" over the source line and "Unlocking...".
        """
        self.clear_container()
        self._label(
            f"{glyph} {g.OK}",
            role="display",
            scale=1.3,
            color=self._colors.palette.success,
            pad="lg",
        )
        self._text(g.WAIT, role="display", color=self._colors.palette.muted)
        unlock_delay = 1500 if self.demo_mode else 2000
        self.root.after(unlock_delay, self.unlock_screen)

    def _on_manual_workout_saved(self, entry: dict) -> None:
        """Show confirmation and unlock after a manual-workout entry is built."""
        self.workout_data = entry
        self._paint_accepted(g.FORM)

    def _on_manual_workout_cancelled(self) -> None:
        """Return to the retry screen when the manual-workout form is cancelled."""
        self._start_phone_check()

    def _handle_startup_phone_result(self, status: str, message: str) -> None:
        """Route to appropriate screen based on startup phone check result."""
        if status == "verified":
            self.workout_data["type"] = "phone_verified"
            self.workout_data["source"] = message
            self._paint_accepted(g.LIFT)
        elif status in ("too_short", "clock_tampered"):
            self._show_retry_and_sick(message, status=status)
        elif status in ("stale", "no_exercises", "not_verified"):
            # Try RunnerUp before showing failure — user may have run instead of lifted.
            self._start_runnerup_fallback(
                lambda: self._show_retry_and_sick(message, status=status)
            )
        else:
            # no_phone or error — try RunnerUp first, then penalty timer.
            self._start_runnerup_fallback(lambda: self._show_phone_penalty(message))

    def _start_runnerup_fallback(self, on_failure: Callable[[], None]) -> None:
        """Check RunnerUp as fallback after phone check fails.

        Shows a waiting screen, runs the check in a background thread, then
        either unlocks (run verified) or calls ``on_failure``.
        Was "Checking RunnerUp..." / "Looking for today's run in RunnerUp".
        """
        self.clear_container()
        self._label(
            f"{g.PHONE} {g.RUN}",
            role="display",
            color=self._colors.palette.warning,
            pad="lg",
        )
        self._text(g.WAIT, role="display", color=self._colors.palette.muted)
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
                self._paint_accepted(g.RUN)
            else:
                self._runnerup_on_failure()
        else:
            self.root.after(500, self._poll_runnerup_fallback)
