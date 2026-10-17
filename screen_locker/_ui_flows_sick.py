"""The "I'm sick" button: one tap marks today sick and unlocks.

A sick day is a date in the shared ``sickdays`` pool (``_sick.py``). There is
no budget, countdown, justification, commitment or debt any more: the tap
writes today into the local pool, pushes it in the background (best
effort, so the phone sees it before the next sickdays-sync tick), raises
tonight's shutdown to the sick floor right
away (``_sick_floor``) and closes the lock. Every other gate reads the same
pool and stands down too.

The button is offered on every screen that can end in a lock or a prompt:
the retry screen, the no-phone penalty screen and both relaxed-day screens.
A refusal (a free day, an unreadable pool) is shown on screen and the lock
stays up.

Next to the button sits a small "choose lockers…" link: the same day, but
with some lockers kept (``_ui_flows_sick_panel``). The button itself still
keeps nothing.

Split out of :mod:`screen_locker._ui_flows` to keep every file under the
250-line cap. Composed back into ``UIFlowsMixin`` there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker._constants import SHUTDOWN_BASE_FILE
from screen_locker._credit_slot import locked_shutdown_state
from screen_locker._sick import mark_today_sick, push_in_background

if TYPE_CHECKING:
    import tkinter as tk


class SickDayFlowMixin:
    """The one-tap sick-day button and what follows it."""

    def _sick_button(self, frame: tk.Widget) -> None:
        """Pack the "I'm sick" button into ``frame``."""
        self._button(
            frame,
            "I'm sick",
            bg=self._colors.palette.warning,
            command=self.mark_sick_and_unlock,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
        # The keep-aware alternative (``_ui_flows_sick_panel``), next to it.
        self._choose_lockers_link(frame)

    def mark_sick_and_unlock(self) -> None:
        """Mark today sick, lift tonight's shutdown to 20:00 and unlock."""
        result = mark_today_sick()
        if not result.ok:
            self._show_sick_refused(result.message)
            return
        self._raise_sick_floor()
        # Best effort and off the UI thread: the unlock never waits for it.
        push_in_background()
        self._unlock_sick_day(
            f"Marked today sick from the lock screen. {result.message}"
        )

    def _raise_sick_floor(self) -> None:
        """Lift tonight's shutdown to the sick floor (a no-op unless sick)."""
        # Now, not at the next 5-minute tick: while this window is up that
        # tick stands down at the instance lock.
        with locked_shutdown_state(SHUTDOWN_BASE_FILE):
            self._apply_sick_floor()

    def _unlock_sick_day(self, detail: str) -> None:
        """Record the sick-day unlock and close the lock.

        Shared by the one-tap button and the keep panel; neither pushes here
        (the panel starts its own sync).
        """
        self._record_decision(locked=False, reason="sick_day_marked", detail=detail)
        self.close()

    def _show_sick_refused(self, message: str) -> None:
        """Say why today could not be marked sick; the lock stays up."""
        self.clear_container()
        self._label(
            "Could not mark today as sick",
            role="display",
            color=self._colors.palette.danger,
            pad="md",
        )
        self._text(message, color=self._colors.palette.warning)
        frame = self._button_row()
        back = (
            self._start_relaxed_day_flow
            if self._relaxed_day_mode
            else self._start_phone_check
        )
        self._button(
            frame,
            "Back",
            bg=self._colors.palette.accent,
            command=back,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
