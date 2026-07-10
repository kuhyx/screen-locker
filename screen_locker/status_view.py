"""Read-only Tkinter status window plus a lightweight i3blocks summary CLI.

Opening or refreshing this window only ever reads files already on disk
(via ``_status_data.gather_status``), with two deliberate exceptions that
only ever *display* a result and never write to ``workout_log.json``:

* "Check Phone" submits ``PhoneVerificationMixin._verify_phone_workout`` to a
  background thread — mirroring the existing submit/poll/``Future`` idiom
  used by ``_ui_flows_relaxed.py``.
* The live Warsaw temperature (see ``_section_temperature``) is fetched via
  ``_temperature.fetch_current_temp_with_status`` on open and on every
  refresh, in its own background thread, bounded to
  ``_temperature.HARD_TIMEOUT_SECONDS`` — the same call the real locker's
  heat-skip check makes, so the window shows what the lock actually sees.

The one exception that *does* write is "Log Manual Workout": a
user-initiated, explicit evidence-form submission (see
``_manual_workout_dialog.ManualWorkoutDialogMixin``) — never a silent log.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # pylint: disable=no-name-in-module
from pathlib import Path
import sys
import tkinter as tk
from typing import TYPE_CHECKING

from screen_locker import _manual_workout
from screen_locker._manual_workout_dialog import ManualWorkoutDialogMixin
from screen_locker._status_data import (
    DayStatus,
    ManualWorkoutBudgetStatus,
    ShutdownProjection,
    SickBudgetStatus,
    StatusSnapshot,
    WeeklySummary,
    format_summary_line,
    gather_status,
)
from screen_locker._temperature import (
    fetch_current_temp_with_status,
)
from screen_locker._temperature_status_mixin import TemperatureStatusMixin
from screen_locker._ui_widgets import UIWidgetsMixin
from screen_locker._weekly_check import (
    WEEKLY_WORKOUT_MINIMUM as _WEEKLY_WORKOUT_MINIMUM,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

    from screen_locker._compliance_state import LockExplanation
    from screen_locker._temperature import TemperatureCheck
    from screen_locker.screen_lock import ScreenLocker

_DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "workout_log.json"


def _make_bare_verifier(log_file: Path) -> ScreenLocker:
    """Build a minimal ``ScreenLocker`` for read-only verification calls.

    Same ``object.__new__`` bypass ``screen_lock.py`` already uses for
    ``--status`` — just enough state for ``PhoneVerificationMixin`` methods
    to run, no Tk lock UI, no ``__init__`` side effects.
    """
    from screen_locker.screen_lock import ScreenLocker

    verifier = object.__new__(ScreenLocker)
    verifier.log_file = log_file
    verifier.workout_data = {}
    return verifier


class StatusWindow(UIWidgetsMixin, ManualWorkoutDialogMixin, TemperatureStatusMixin):
    """Thin Tk view over a :class:`StatusSnapshot`.

    Formatting logic lives in ``_status_data``, not here.
    """

    def __init__(
        self,
        root: tk.Tk,
        snapshot: StatusSnapshot,
        *,
        on_refresh: Callable[[], None],
        log_file: Path = _DEFAULT_LOG_FILE,
        verifier_factory: Callable[[Path], ScreenLocker] = _make_bare_verifier,
        temperature_fetcher: Callable[
            [str], TemperatureCheck
        ] = fetch_current_temp_with_status,
    ) -> None:
        """Build the window's container and render *snapshot* immediately."""
        self.root = root
        self.on_refresh = on_refresh
        self.log_file = log_file
        self.verifier_factory = verifier_factory
        self.temperature_fetcher = temperature_fetcher
        self.demo_mode = True  # only affects UIWidgetsMixin._button's cursor
        self._phone_future: Future[tuple[str, str]] | None = None
        self._phone_check_result: tuple[str, str] | None = None
        self._manual_workout_saved_message: str | None = None
        self._temp_future: Future[TemperatureCheck] | None = None
        self._temp_result: TemperatureCheck | None = None
        self._last_snapshot = snapshot
        self.container = tk.Frame(root, bg="#1a1a1a")
        self.container.pack(fill="both", expand=True)
        self._start_temperature_check()
        self.render(snapshot)

    def render(self, snapshot: StatusSnapshot) -> None:
        """Redraw the whole window from *snapshot*."""
        self._last_snapshot = snapshot
        self.clear_container()
        self._label("Workout Status", font_size=28, pady=15)
        self._section_today(self.container, snapshot.today)
        self._section_week(self.container, snapshot.week)
        self._section_lock_explanation(self.container, snapshot.lock_explanation)
        self._section_temperature(self.container)
        self._section_sick_budget(self.container, snapshot.sick_budget)
        self._section_manual_workout_budget(
            self.container, snapshot.manual_workout_budget
        )
        self._section_shutdown(self.container, snapshot.shutdown)
        if self._phone_check_result is not None:
            status, message = self._phone_check_result
            color = "#00cc44" if status == "verified" else "#ff8844"
            self._text(f"Phone check ({status}): {message}", font_size=13, color=color)
        if self._manual_workout_saved_message is not None:
            self._text(
                self._manual_workout_saved_message, font_size=13, color="#00cc44"
            )
        frame = self._button_row()
        self._button(
            frame,
            "Check Phone",
            bg="#0066cc",
            command=self._on_check_phone_clicked,
            width=14,
        ).pack(side="left", padx=8)
        if not _manual_workout.is_budget_exhausted(self.log_file):
            self._button(
                frame,
                "Log Manual Workout",
                bg="#0088cc",
                command=self._show_manual_workout_form,
                width=16,
            ).pack(side="left", padx=8)
        self._button(
            frame, "Refresh", bg="#006600", command=self._on_refresh_clicked, width=10
        ).pack(side="left", padx=8)
        self._button(
            frame, "Close", bg="#aa0000", command=self.root.destroy, width=8
        ).pack(side="left", padx=8)

    def _section_today(self, parent: tk.Widget, day: DayStatus) -> None:
        """Render today's outcome."""
        del parent
        mark = "✓" if day.counted else ("😷" if day.is_sick_day else "—")
        entry_str = day.entry_type or (
            "sick day" if day.is_sick_day else "no entry yet"
        )
        self._text(
            f"{mark} Today ({day.label}): {entry_str}",
            font_size=18,
            color="#aaffaa" if day.counted else "#ffaa00",
        )
        if day.source:
            self._text(day.source, font_size=12, color="#888888", pady=2)

    def _section_week(self, parent: tk.Widget, week: WeeklySummary) -> None:
        """Render this ISO week's per-day breakdown and totals."""
        del parent
        self._label(
            f"This Week: {week.counted_count}/{week.minimum}", font_size=18, pady=8
        )
        for day in week.days:
            mark = "✓" if day.counted else ("😷" if day.is_sick_day else "·")
            entry_str = day.entry_type or (
                "sick day" if day.is_sick_day else "no entry"
            )
            self._text(
                f"{mark} {day.label}: {entry_str}",
                font_size=12,
                color="#cccccc",
                pady=1,
            )
        if week.remaining > 0:
            self._text(
                f"Need {week.remaining} more this week.", font_size=13, color="#ffaa00"
            )
        elif week.extra > 0:
            self._text(
                f"{week.extra} above the weekly minimum!", font_size=13, color="#00cc44"
            )

    def _section_lock_explanation(
        self, parent: tk.Widget, expl: LockExplanation
    ) -> None:
        """Render why the lock did/didn't fire today, plus its evaluation trace."""
        del parent
        self._label("Why the lock did/didn't fire", font_size=16, pady=8)
        self._text(
            expl.reason, font_size=13, color="#ff4444" if expl.fired else "#00cc44"
        )
        if expl.auto_upgrade.would_attempt:
            self._text(
                f"Pending auto-upgrade: {expl.auto_upgrade.reason}",
                font_size=11,
                color="#ffaa00",
            )

    def _section_sick_budget(self, parent: tk.Widget, sick: SickBudgetStatus) -> None:
        """Render rolling sick-day budget usage."""
        del parent
        self._label("Sick Budget", font_size=16, pady=8)
        self._text(
            f"{sick.used_7d}/{sick.budget_7d} week · {sick.used_30d}/{sick.budget_30d} "
            f"month · {sick.used_90d}/{sick.budget_90d} quarter · debt {sick.debt}",
            font_size=12,
            color="#ff4444" if sick.exhausted else "#cccccc",
        )

    def _section_manual_workout_budget(
        self, parent: tk.Widget, manual: ManualWorkoutBudgetStatus
    ) -> None:
        """Render rolling manual-workout budget usage."""
        del parent
        self._label("Manual Workout Budget", font_size=16, pady=8)
        self._text(
            f"{manual.used_7d}/{manual.budget_7d} week · "
            f"{manual.used_30d}/{manual.budget_30d} month",
            font_size=12,
            color="#ff4444" if manual.exhausted else "#cccccc",
        )

    def _section_shutdown(
        self, parent: tk.Widget, shutdown: ShutdownProjection
    ) -> None:
        """Render tonight's live config, rest-of-week, and next-week preview."""
        del parent
        self._label("Shutdown Time", font_size=16, pady=8)
        if shutdown.tonight is not None:
            mon_wed_hour, thu_sun_hour, _morning = shutdown.tonight
            self._text(
                f"Live config — Mon-Wed {mon_wed_hour:02d}:00, "
                f"Thu-Sun {thu_sun_hour:02d}:00",
                font_size=12,
            )
        else:
            self._text(
                "Live shutdown config unavailable.", font_size=12, color="#ff8844"
            )
        rest_line = ", ".join(
            f"{d.label} {d.hour:02d}:00" for d in shutdown.rest_of_week
        )
        self._text(f"Rest of week: {rest_line}", font_size=10, color="#cccccc")
        next_line = ", ".join(
            f"{d.label} {d.hour:02d}:00" for d in shutdown.next_week_preview
        )
        self._text(
            f"Next week (speculative): {next_line}", font_size=10, color="#888888"
        )
        self._text(shutdown.explanation, font_size=10, color="#666666")

    def _on_refresh_clicked(self) -> None:
        """Clear any stale phone-check/temperature results, re-check both."""
        self._phone_check_result = None
        self._temp_result = None
        self._start_temperature_check()
        self.on_refresh()

    def _on_check_phone_clicked(self) -> None:
        """Submit a background phone-verification check and start polling it."""
        self._phone_check_result = None
        verifier = self.verifier_factory(self.log_file)
        executor = ThreadPoolExecutor(max_workers=1)
        self._phone_future = executor.submit(verifier._verify_phone_workout)
        executor.shutdown(wait=False)
        self._poll_phone_check()

    def _poll_phone_check(self) -> None:
        """Poll the background phone-check future until it resolves."""
        if self._phone_future is not None and self._phone_future.done():
            status, message = self._phone_future.result()
            self._on_phone_check_result(status, message)
        else:
            self.root.after(500, self._poll_phone_check)

    def _on_phone_check_result(self, status: str, message: str) -> None:
        """Display the phone-check result. Never logs — display only."""
        self._phone_check_result = (status, message)
        self.render(gather_status())

    def _on_manual_workout_saved(self, entry: dict) -> None:
        """Persist the manual-workout entry via a bare verifier, then refresh.

        Unlike the phone check, this one deliberate path does write to
        ``workout_log.json`` — the user just explicitly filled out and
        submitted the evidence form, so this is not a silent log. Uses the
        same ``_apply_workout_credit`` the locked screen's ``unlock_screen``
        uses, so this voluntary path earns the identical shutdown-later
        bonus / debt-clear / extra-bonus credit (guarded against being
        applied twice on the same day).
        """
        verifier = self.verifier_factory(self.log_file)
        verifier.workout_data = entry
        credit = verifier._apply_workout_credit()
        lines = [f"Manual workout logged: {entry.get('source', '')}"]
        if credit.already_counted_today:
            lines.append(
                "(Today already had a counted workout — no extra credit applied.)"
            )
        else:
            if credit.shutdown_adjusted:
                lines.append("Shutdown time +2h later!")
            if credit.extra_bonus_delta > 0:
                extra_n = credit.weekly_count - _WEEKLY_WORKOUT_MINIMUM
                lines.append(
                    f"Extra workout #{extra_n}! +{credit.extra_bonus_delta}h tonight"
                )
            if credit.new_debt is not None:
                lines.append(f"Workout debt: {credit.new_debt}")
        self._manual_workout_saved_message = "\n".join(lines)
        self.render(gather_status())

    def _on_manual_workout_cancelled(self) -> None:
        """Return to the main status view without saving anything."""
        self.render(gather_status())


def _compliance_state_word(snapshot: StatusSnapshot) -> str:
    """One-word compliance state for the tray icon: ``ok`` / ``warn`` / ``lock``.

    ``lock`` — the lock would fire right now (no skip condition applies).
    ``warn`` — not locked, but this week's minimum isn't met yet.
    ``ok`` — not locked and the weekly minimum is already met.
    """
    if snapshot.lock_explanation.fired:
        return "lock"
    if snapshot.week.remaining > 0:
        return "warn"
    return "ok"


def main(argv: list[str] | None = None) -> None:
    """Entry point: ``--summary``/``--state`` print one line; else opens the window."""
    args = sys.argv[1:] if argv is None else argv
    if "--summary" in args:
        print(format_summary_line(gather_status()))
        return
    if "--state" in args:
        print(_compliance_state_word(gather_status()))
        return

    root = tk.Tk()
    root.title("Workout Status")
    root.configure(bg="#1a1a1a")
    root.minsize(560, 200)

    def refresh() -> None:
        window.render(gather_status())

    window = StatusWindow(root, gather_status(), on_refresh=refresh)
    root.mainloop()


if __name__ == "__main__":
    main()
