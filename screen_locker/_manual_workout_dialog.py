"""Manual (unverified) workout evidence-form dialog mixin.

Composed onto both ``ScreenLocker`` (locked-out entry point) and
``StatusWindow`` (voluntary, anytime entry point). Host classes must
implement two hooks:

- ``_on_manual_workout_saved(entry: dict) -> None`` — called with the built
  ``workout_data`` dict once the form validates; the host decides how to
  persist it (and, for ``ScreenLocker``, unlock afterward).
- ``_on_manual_workout_cancelled() -> None`` — called when BACK is pressed.

The form's activity-details section is sport-specific (see
``_manual_workout.SPORT_CHOICES``): choosing a sport swaps in that sport's
fields via ``_on_mw_sport_changed`` rather than one generic free-text blob.
"""

from __future__ import annotations

import logging
import tkinter as tk

from screen_locker import _manual_workout
from screen_locker._constants import (
    MANUAL_WORKOUT_DESCRIPTION_MIN_CHARS,
    MANUAL_WORKOUT_REFLECTION_MIN_CHARS,
)
from screen_locker._manual_workout_widgets import ManualWorkoutFormWidgetsMixin

_logger = logging.getLogger(__name__)

_SPORT_LABEL_TO_CODE = {
    label: code for code, label in _manual_workout.SPORT_LABELS.items()
}


class ManualWorkoutDialogMixin(ManualWorkoutFormWidgetsMixin):
    """Renders the manual-workout evidence form and handles submission."""

    def _show_manual_workout_form(self) -> None:
        """Render the manual-workout evidence form, or a budget-exhausted note."""
        self.clear_container()
        self._label("Log Manual Workout", color=self._colors.accent, pad="xs")
        if _manual_workout.is_budget_exhausted(self.log_file):
            self._text(
                "Manual-workout budget exhausted for this window.",
                color=self._colors.danger,
            )
            self._text(
                _manual_workout.budget_summary(self.log_file),
                color=self._colors.muted,
            )
            row = self._button_row()
            self._button(
                row,
                "BACK",
                bg=self._colors.field_bg,
                command=self._on_manual_workout_cancelled,
                width=12,
            ).pack(side="left", padx=self._colors.space("sm"))
            return
        self._text(
            _manual_workout.budget_summary(self.log_file),
            role="label",
            color=self._colors.accent,
            pad="xs",
        )
        self._build_manual_workout_form()

    def _mw_scrollable_form(self) -> tk.Frame:
        """Create the two-column form frame inside the surface's viewport.

        This used to build its *own* ``Canvas`` + ``Scrollbar`` viewport, which
        had three problems that are all gone by deletion now that the surface
        container is itself a :class:`~gatelock.ScrollableSurface`:

        1. **Scrolling was pointer-only.** ``tk.Canvas`` has no class-level key
           bindings, so ``::tk::FocusOK`` rejected it as a focus stop, and the
           canvas bound no ``<MouseWheel>``, ``<Prior>``/``<Next>`` or arrows.
           The scrollbar thumb had to be *dragged* -- inside a lock that cannot
           be dismissed without submitting this form.
        2. **Focus walked off-screen.** Canvas clipping does not unmap a child,
           so every below-the-fold field stayed ``winfo viewable`` and stayed in
           the tab ring while Tk never scrolled to follow focus. Tab led to
           fields the user could neither see nor bring into view.
        3. **The height was a magic fraction.** ``height=0.7 * toplevel`` sat
           above ~230-290px of fixed chrome (title, budget line, error label,
           and a 24pt button row), so the constraint was ``0.3 * H >= chrome``:
           satisfied at 1080p, violated at 768p, where SUBMIT/BACK were pushed
           off the bottom of a centred, unscrollable container.

        Still built on the primary surface only -- an independently scrolled
        copy per monitor would show two different parts of one form.
        """
        form = tk.Frame(self.container.first, bg=self._colors.bg)
        # No outer gap: the budget line above and the first section heading
        # below already separate the grid, and on a 1024x600 panel this form
        # fits by single-digit pixels.
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(0, weight=1, uniform="mw")
        form.grid_columnconfigure(1, weight=1, uniform="mw")
        return form

    def _build_manual_workout_form(self) -> None:
        """Build the two-column evidence form and submit/back buttons.

        Large labels/inputs and a screen-filling grid (see
        ``_mw_scrollable_form``) so the form is usable with a keyboard while
        locked out, rather than a cramped narrow column.
        """
        form = self._mw_scrollable_form()

        # Independent 2-column grid cursor per master (form + sport sub-frames).
        self._mw_grid_counters: dict[int, int] = {}
        self._mw_vars: dict[str, tk.StringVar] = {}
        self._mw_int_vars: dict[str, tk.IntVar] = {}
        self._mw_rpe_var = tk.IntVar(value=5)
        self._mw_text_widgets: dict[str, tk.Text] = {}

        self._mw_section(form, "Basics")
        self._mw_sport_row(form)
        self._mw_vars["start_time"] = self._mw_entry(
            form, "Start time (HH:MM):", focus=True
        )
        self._mw_vars["end_time"] = self._mw_entry(form, "End time (HH:MM):")

        self._mw_section(form, "Location & logistics")
        self._mw_vars["location_name"] = self._mw_entry(form, "Location name:")
        self._mw_vars["transport_method"] = self._mw_entry(
            form, "How did you get there?"
        )
        self._mw_vars["cost"] = self._mw_entry(form, "Cost (e.g. 40 PLN):")
        self._mw_vars["reservation_phone"] = self._mw_entry(
            form, "Reservation phone number (if booked by phone, optional):"
        )

        self._mw_section(form, "Activity details")
        # Both sport sub-frames occupy the same full-width grid slot; only the
        # selected one is shown (see _on_mw_sport_changed).
        act_row = self._mw_next_full_row(form)
        self._mw_tt_frame = tk.Frame(form, bg=self._colors.bg)
        self._mw_other_frame = tk.Frame(form, bg=self._colors.bg)
        for sport_frame in (self._mw_tt_frame, self._mw_other_frame):
            sport_frame.grid_columnconfigure(0, weight=1, uniform="mwact")
            sport_frame.grid_columnconfigure(1, weight=1, uniform="mwact")
            sport_frame.grid(
                row=act_row,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=self._colors.space("sm"),
                pady=self._colors.space("xs"),
            )
        self._build_table_tennis_fields(self._mw_tt_frame)
        self._build_other_sport_fields(self._mw_other_frame)
        self._mw_rpe_row(form)
        self._mw_vars["techniques_practiced"] = self._mw_entry(
            form, "Techniques/focus areas practiced (optional):"
        )
        self._mw_vars["warm_up_minutes"] = self._mw_entry(
            form, "Warm-up duration (optional):"
        )
        self._mw_vars["pain_or_injury"] = self._mw_entry(
            form, "Pain or injury notes (optional, default none):"
        )
        self._on_mw_sport_changed(
            _manual_workout.SPORT_LABELS[_manual_workout.SPORT_TABLE_TENNIS]
        )

        self._mw_section(form, "Reflection")
        self._mw_text_widgets["went_well"] = self._mw_textbox(
            form,
            f"What went well (min {MANUAL_WORKOUT_REFLECTION_MIN_CHARS} chars):",
        )
        self._mw_text_widgets["to_improve"] = self._mw_textbox(
            form,
            f"What to improve (min {MANUAL_WORKOUT_REFLECTION_MIN_CHARS} chars):",
        )
        self._mw_text_widgets["overall_feeling"] = self._mw_textbox(
            form,
            "Overall feeling about the session "
            f"(min {MANUAL_WORKOUT_REFLECTION_MIN_CHARS} chars):",
        )

        self._mw_error_label = self._text(
            "", role="label", color=self._colors.danger, pad="xs"
        )
        button_row = self._button_row()
        self._button(
            button_row,
            "SUBMIT",
            bg=self._colors.accent,
            command=self._submit_manual_workout_form,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            button_row,
            "BACK",
            bg=self._colors.field_bg,
            command=self._on_manual_workout_cancelled,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))

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

    def _submit_manual_workout_form(self) -> None:
        """Validate the form and either show an error or save + notify host."""
        try:
            rpe = int(self._mw_rpe_var.get())
        except (tk.TclError, ValueError) as exc:
            _logger.warning(
                "Manual workout RPE is not an integer (%s) — submitting it as "
                "0, which the form validator will reject",
                exc,
            )
            rpe = 0
        sport = self._current_mw_sport()
        draft = _manual_workout.ManualWorkoutDraft(
            sport=sport,
            start_time=self._mw_vars["start_time"].get(),
            end_time=self._mw_vars["end_time"].get(),
            location_name=self._mw_vars["location_name"].get(),
            transport_method=self._mw_vars["transport_method"].get(),
            cost=self._mw_vars["cost"].get(),
            rpe=rpe,
            went_well=self._mw_text_widgets["went_well"].get("1.0", "end"),
            to_improve=self._mw_text_widgets["to_improve"].get("1.0", "end"),
            overall_feeling=self._mw_text_widgets["overall_feeling"].get("1.0", "end"),
            reservation_phone=self._mw_vars["reservation_phone"].get(),
            techniques_practiced=self._mw_vars["techniques_practiced"].get(),
            warm_up_minutes=self._mw_vars["warm_up_minutes"].get(),
            pain_or_injury=self._mw_vars["pain_or_injury"].get() or "none",
            matches_won=self._mw_int_value("matches_won"),
            matches_lost=self._mw_int_value("matches_lost"),
            sets_won=self._mw_int_value("sets_won"),
            sets_lost=self._mw_int_value("sets_lost"),
            racket=self._mw_vars["racket"].get(),
            balls=self._mw_vars["balls"].get(),
            activity_type_other=self._mw_vars["activity_type_other"].get(),
            activity_details=self._mw_text_widgets["activity_details"].get(
                "1.0", "end"
            ),
            equipment=self._mw_vars["equipment"].get(),
        )
        error = _manual_workout.validate_manual_workout(draft)
        if error is not None:
            self._mw_error_label.config(text=error)
            return
        entry = _manual_workout.build_entry(draft)
        # Record the manual for cross-device sync (published on the next lock
        # startup). Local + best-effort — never blocks saving/unlocking.
        self._on_manual_workout_saved(entry)
