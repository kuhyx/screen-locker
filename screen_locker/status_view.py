"""Read-only Tkinter status window plus a lightweight i3blocks summary CLI.

Opening or refreshing this window only ever reads files already on disk
(via ``_status_data.gather_status``). The live Warsaw temperature (see
``_section_temperature``) is fetched via
``_temperature.fetch_current_temp_with_status`` on open and on every refresh,
in its own background thread, bounded to ``_temperature.HARD_TIMEOUT_SECONDS``
— the same call the real locker's heat-skip check makes, so the window shows
what the lock actually sees. That fetch is display-only and never writes.

Two user-initiated buttons *do* write to ``log.json`` (never a silent
log):

* "Check Phone" runs ``PhoneVerificationMixin._verify_phone_workout`` and, when
  that finds nothing, ``RunnerUpVerificationMixin._verify_runnerup_workout`` as
  a fallback — the same StrongLifts→RunnerUp chain the locked screen uses. On a
  verified workout it writes the entry and applies the shutdown reward via
  ``_apply_workout_credit`` (guarded against double-crediting on the same day),
  mirroring the submit/poll/``Future`` idiom of ``_ui_flows.py``.
* "Log Manual Workout" is a user-initiated, explicit evidence-form submission
  (see ``_manual_workout_dialog.ManualWorkoutDialogMixin``).
"""

from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import LockConfig

from screen_locker import _manual_workout
from screen_locker._manual_workout_dialog import ManualWorkoutDialogMixin
from screen_locker._status_data import (
    StatusSnapshot,
    format_summary_line,
    gather_status,
)
from screen_locker._status_projection import compliance_state_word
from screen_locker._status_sections import StatusSectionsMixin
from screen_locker._status_view_verify import PhoneCheckMixin, _make_bare_verifier
from screen_locker._surface_group import FrameGroup
from screen_locker._sync_status import format_sync_line, gather_sync_status
from screen_locker._temperature import (
    fetch_current_temp_with_status,
)
from screen_locker._temperature_status_mixin import TemperatureStatusMixin
from screen_locker._ui_widgets import UIWidgetsMixin

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

    from screen_locker._temperature import TemperatureCheck
    from screen_locker.screen_lock import ScreenLocker

_DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "log.json"
_STATUS_COLORS = LockConfig()


class StatusWindow(
    UIWidgetsMixin,
    ManualWorkoutDialogMixin,
    TemperatureStatusMixin,
    PhoneCheckMixin,
    StatusSectionsMixin,
):
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
        self._phone_future: Future[tuple[str | None, str, str, str | None]] | None = (
            None
        )
        self._phone_check_result: tuple[str, str] | None = None
        self._credit_message: str | None = None
        self._temp_future: Future[TemperatureCheck] | None = None
        self._temp_result: TemperatureCheck | None = None
        self._last_snapshot = snapshot
        self._colors = _STATUS_COLORS
        # A group of one: this window has no lock and no per-output surfaces,
        # but it shares UIWidgetsMixin's factory with the locker, which now
        # builds through a group. Filling the window rather than centring, so
        # this is built here instead of via FrameGroup.single().
        frame = tk.Frame(root, bg=self._colors.bg)
        frame.pack(fill="both", expand=True)
        self.container = FrameGroup([frame])
        self._start_temperature_check()
        self.render(snapshot)

    def render(self, snapshot: StatusSnapshot) -> None:
        """Redraw the whole window from *snapshot*."""
        self._last_snapshot = snapshot
        self.clear_container()
        self._label("Workout Status", role="title", pad="md")
        self._section_today(self.container, snapshot.today)
        self._section_week(self.container, snapshot.week)
        self._section_lock_explanation(self.container, snapshot.lock_explanation)
        self._section_temperature(self.container)
        self._section_sick_budget(self.container, snapshot.sick_budget)
        self._section_manual_workout_budget(
            self.container, snapshot.manual_workout_budget
        )
        self._section_sync_backend(self.container)
        self._section_shutdown(self.container, snapshot.shutdown)
        if self._phone_check_result is not None:
            status, message = self._phone_check_result
            color = (
                self._colors.success if status == "verified" else self._colors.warning
            )
            self._text(f"Phone check ({status}): {message}", role="body", color=color)
        if self._credit_message is not None:
            self._text(self._credit_message, role="body", color=self._colors.success)
        # "Check Phone"/"Log Manual Workout" are the primary write actions
        # (accent, high contrast per rule 3); "Refresh"/"Close" are secondary
        # utility actions (muted) -- two tiers instead of four arbitrary hues.
        frame = self._button_row()
        self._button(
            frame,
            "Check Phone",
            bg=self._colors.accent,
            command=self._on_check_phone_clicked,
            width=14,
        ).pack(side="left", padx=self._colors.space("sm"))
        if not _manual_workout.is_budget_exhausted(self.log_file):
            self._button(
                frame,
                "Log Manual Workout",
                bg=self._colors.accent,
                command=self._show_manual_workout_form,
                width=16,
            ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            frame,
            "Refresh",
            bg=self._colors.field_bg,
            command=self._on_refresh_clicked,
            width=10,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            frame,
            "Close",
            bg=self._colors.field_bg,
            command=self.root.destroy,
            width=8,
        ).pack(side="left", padx=self._colors.space("sm"))

    def _on_refresh_clicked(self) -> None:
        """Clear any stale phone-check/credit/temperature results, re-check both."""
        self._phone_check_result = None
        self._credit_message = None
        self._temp_result = None
        self._start_temperature_check()
        self.on_refresh()

    def _on_manual_workout_saved(self, entry: dict) -> None:
        """Persist the manual-workout entry via a bare verifier, then refresh.

        Unlike the phone check, this one deliberate path does write to
        ``log.json`` — the user just explicitly filled out and
        submitted the evidence form, so this is not a silent log. Uses the
        same ``_apply_workout_credit`` the locked screen's ``unlock_screen``
        uses, so this voluntary path earns the identical shutdown-later
        bonus / debt-clear / extra-bonus credit (guarded against being
        applied twice on the same day).
        """
        verifier = self.verifier_factory(self.log_file)
        verifier.workout_data = entry
        credit = verifier._apply_workout_credit()
        self._credit_message = "\n".join(
            self._credit_result_lines(
                f"Manual workout logged: {entry.get('source', '')}", credit
            )
        )
        self.render(gather_status())

    def _on_manual_workout_cancelled(self) -> None:
        """Return to the main status view without saving anything."""
        self.render(gather_status())


def main(argv: list[str] | None = None) -> None:
    """Entry point: ``--summary``/``--state``/``--sync`` print one line.

    With no flag, opens the status window.
    """
    args = sys.argv[1:] if argv is None else argv
    if "--summary" in args:
        print(format_summary_line(gather_status()))
        return
    if "--state" in args:
        print(compliance_state_word(gather_status()))
        return
    if "--sync" in args:
        # On-disk only, like the other two -- safe on an i3blocks tick.
        print(format_sync_line(gather_sync_status()))
        return

    root = tk.Tk()
    root.title("Workout Status")
    root.configure(bg=_STATUS_COLORS.bg)
    root.minsize(560, 200)

    def refresh() -> None:
        window.render(gather_status())

    window = StatusWindow(root, gather_status(), on_refresh=refresh)
    root.mainloop()


if __name__ == "__main__":
    main()
