"""Sport-specific rows of the manual-workout evidence form.

Split out of :mod:`screen_locker._manual_workout_dialog` to keep every file
under the 250-line cap. Composed back into ``ManualWorkoutDialogMixin`` there,
so both host classes (``ScreenLocker`` and ``StatusWindow``) are unchanged.

Choosing a sport swaps in that sport's fields rather than showing one generic
free-text blob -- see ``_manual_workout.SPORT_CHOICES``.
"""

from __future__ import annotations

import logging
import tkinter as tk

from screen_locker import _manual_workout
from screen_locker._constants import MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS

_logger = logging.getLogger(__name__)

_SPORT_LABEL_TO_CODE = {
    label: code for code, label in _manual_workout.SPORT_LABELS.items()
}


class ManualWorkoutSportFieldsMixin:
    """Builds the sport picker and the per-sport detail rows."""

    def _mw_sport_row(self, parent: tk.Widget) -> None:
        """Add the sport-selector radio buttons; swaps the activity section.

        CANONICAL ACCOUNT OF THE 2026-07-26 BUG -- other files point here.

        This was a ``tk.OptionMenu``. A posted Tk menu is a separate
        override-redirect toplevel that takes the Tk grab for itself, and
        gatelock's 1 s recovery tick killed it within a second of opening:
        ``_surfaces.enforce()`` lifts the lock surface over the menu, and
        ``_reassert_grab()`` saw the grab sitting on the menu rather than the
        root and yanked it back. The selector stayed stuck on "Table tennis"
        while locked, and a walk got logged in the table-tennis form.

        Radio buttons are ordinary children of the surface: they lift with it
        and live inside the root's grab tree, so neither mechanism can reach
        them. Nothing on a lock surface may open a popup window --
        ``tests/test_no_popup_widgets.py`` enforces that statically and
        ``scripts/verify_lock_popup_safety.py`` behaviourally.
        """
        self._mw_sport_var = tk.StringVar(
            value=_manual_workout.SPORT_LABELS[_manual_workout.SPORT_TABLE_TENNIS]
        )
        row = tk.Frame(parent, bg=self._colors.bg)
        tk.Label(
            row,
            text="Sport:",
            font=self._colors.font("body"),
            fg=self._colors.fg,
            bg=self._colors.bg,
        ).pack(side="left", padx=self._colors.space("xs"))
        for label in _manual_workout.SPORT_LABELS.values():
            tk.Radiobutton(
                row,
                text=label,
                value=label,
                variable=self._mw_sport_var,
                # Radiobutton's command takes no argument -- bind the label.
                command=lambda chosen=label: self._on_mw_sport_changed(chosen),
                font=self._colors.font("body"),
                fg=self._colors.fg,
                bg=self._colors.bg,
                activeforeground=self._colors.fg,
                activebackground=self._colors.bg,
                # Without selectcolor the indicator is a white blob on the dark
                # overlay; the OptionMenu was the one unstyled widget in this
                # form, which likely added to it reading as dead.
                selectcolor=self._colors.field_bg,
                highlightthickness=0,
            ).pack(side="left", padx=self._colors.space("xs"))
        self._mw_grid(parent, row, full=True)

    def _on_mw_sport_changed(self, selected_label: str) -> None:
        """Show the fields for the newly-selected sport, hide the other's.

        Both frames share one grid slot; ``grid_remove`` hides a frame while
        remembering its cell options so ``grid`` restores it in place.
        """
        sport = _SPORT_LABEL_TO_CODE.get(
            selected_label, _manual_workout.SPORT_TABLE_TENNIS
        )
        if sport == _manual_workout.SPORT_TABLE_TENNIS:
            self._mw_other_frame.grid_remove()
            self._mw_tt_frame.grid()
        else:
            self._mw_tt_frame.grid_remove()
            self._mw_other_frame.grid()

    def _build_table_tennis_fields(self, parent: tk.Widget) -> None:
        """Build the table-tennis-specific score/equipment fields."""
        self._mw_int_vars["matches_won"] = self._mw_int_field(parent, "Matches won:")
        self._mw_int_vars["matches_lost"] = self._mw_int_field(parent, "Matches lost:")
        self._mw_int_vars["sets_won"] = self._mw_int_field(parent, "Sets won:")
        self._mw_int_vars["sets_lost"] = self._mw_int_field(parent, "Sets lost:")
        self._mw_vars["racket"] = self._mw_entry(parent, "Racket used:")
        self._mw_vars["balls"] = self._mw_entry(parent, "Balls used:")

    def _build_other_sport_fields(self, parent: tk.Widget) -> None:
        """Build the generic "other sport" fields."""
        self._mw_vars["activity_type_other"] = self._mw_entry(
            parent, "What sport/activity:"
        )
        self._mw_text_widgets["activity_details"] = self._mw_textbox(
            parent,
            f"What was done (min {MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS} chars):",
        )
        self._mw_vars["equipment"] = self._mw_entry(
            parent, "Equipment used (optional):"
        )

    def _current_mw_sport(self) -> str:
        """Return the internal sport code for the currently-selected label."""
        return _SPORT_LABEL_TO_CODE.get(
            self._mw_sport_var.get(), _manual_workout.SPORT_TABLE_TENNIS
        )

    def _mw_int_value(self, key: str) -> int:
        """Read an int Spinbox var, defaulting to 0 on an invalid value."""
        try:
            return int(self._mw_int_vars[key].get())
        except (tk.TclError, ValueError) as exc:
            _logger.warning(
                "Manual workout field %r holds a non-integer value (%s) — "
                "recording it as 0",
                key,
                exc,
            )
            return 0
