"""Workout-date field of the manual-workout form, and the future-dated path.

Split out of :mod:`screen_locker._manual_workout_dialog` to keep every file
under the 250-line cap; composed back into ``ManualWorkoutDialogMixin`` there,
so both hosts (``ScreenLocker`` and ``StatusWindow``) are unchanged.

A manual workout may be dated today up to 7 days ahead. Today's takes the
host's ordinary save path (which, on the lock screen, unlocks). A FUTURE one
must not: it earns nothing today, so it is handed to ``_manual_schedule`` and
the form shows a "scheduled" screen that returns to the host's cancelled hook
-- never ``_on_manual_workout_saved``, which would unlock today.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from screen_locker._day import today_str
from screen_locker._manual_future import (
    budget_closed_for_all_days,
    is_future_date,
    validate_workout_date,
)
from screen_locker._manual_pending import local_pending_records, pending_future_dates
from screen_locker._manual_schedule import budget_error, schedule_future_workout
from screen_locker._ui_widgets import disable_paste

if TYPE_CHECKING:
    from screen_locker._manual_workout import ManualWorkoutDraft


class ManualWorkoutDateMixin:
    """Date row, budget gate and future-dated submission of the manual form."""

    def _mw_budget_closed(self) -> bool:
        """True if no day in today..today+7 has room (local ledger, no network)."""
        pending = pending_future_dates(self.log_file, local_pending_records())
        return budget_closed_for_all_days(self.log_file, pending.values())

    def _mw_date_in_row(self, row: tk.Frame) -> None:
        """Pack the workout-date entry (prefilled with today) into ``row``.

        Called from the sport row rather than given a row of its own: the
        lock cannot scroll, and the form already fills a 768px panel
        (``scripts/verify_screen_fits.py``), so the field has to cost no height.
        """
        var = tk.StringVar(value=today_str())
        self._mw_vars["date"] = var
        entry = tk.Entry(
            row,
            textvariable=var,
            width=11,
            font=self._colors.font("label"),
            bg=self._colors.palette.field_bg,
            fg=self._colors.palette.fg,
            insertbackground=self._colors.palette.fg,
            **self._colors.focus_kwargs(),
        )
        entry.pack(side="right", padx=self._colors.space("xs"))
        disable_paste(entry)
        tk.Label(
            row,
            text="Workout date (today to +7 days):",
            font=self._colors.font("label"),
            fg=self._colors.palette.fg,
            bg=self._colors.palette.bg,
        ).pack(side="right", padx=self._colors.space("xs"))

    def _mw_handled_by_date(self, draft: ManualWorkoutDraft) -> bool:
        """Apply the date and budget rules; True if the submit is fully handled.

        Handled means an error is on screen or a future entry was scheduled;
        False means the date is today and within budget, so the caller
        carries on with the host's ordinary save.
        """
        date = self._mw_vars["date"].get().strip()
        error = validate_workout_date(date)
        future = error is None and is_future_date(date)
        if error is None and not future:
            error = budget_error(self.log_file, date)
        if error is not None:
            self._mw_error_label.config(text=error)
            return True
        if not future:
            return False
        result = schedule_future_workout(self.log_file, draft, date)
        if not result.scheduled:
            self._mw_error_label.config(text=result.reason)
            return True
        self._show_manual_workout_scheduled(result.reason)
        return True

    def _show_manual_workout_scheduled(self, reason: str) -> None:
        """Confirm a future entry and go back; it does NOT unlock anything."""
        self.clear_container()
        self._label(
            "✓ Workout Scheduled",
            role="display",
            scale=1.3,
            color=self._colors.palette.success,
            pad="lg",
        )
        self._text(reason, role="subtitle", color=self._colors.palette.success)
        self._text(
            "Nothing is credited today. It counts by itself on that date, and "
            "can be deleted in the phone app until then.",
            color=self._colors.palette.muted,
        )
        row = self._button_row()
        self._button(
            row,
            "OK",
            bg=self._colors.palette.accent,
            command=self._on_manual_workout_cancelled,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
