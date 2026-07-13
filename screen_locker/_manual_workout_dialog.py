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
from screen_locker._manual_push import record_pc_manual
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
        self._label("Log Manual Workout", color="#0088cc", pady=10)
        if _manual_workout.is_budget_exhausted(self.log_file):
            self._text(
                "Manual-workout budget exhausted for this window.",
                color="#ff4444",
            )
            self._text(_manual_workout.budget_summary(self.log_file), color="#888888")
            row = self._button_row()
            self._button(
                row,
                "BACK",
                bg="#aa0000",
                command=self._on_manual_workout_cancelled,
                width=12,
            ).pack(side="left", padx=10)
            return
        self._text(_manual_workout.budget_summary(self.log_file), color="#88ccff")
        self._build_manual_workout_form()

    def _mw_scrollable_form(self) -> tk.Frame:
        """Create the scrollable canvas + inner two-column form frame.

        The canvas is given a concrete size from the toplevel so the fullscreen
        lock screen's centered container can't shrink-wrap to a narrow column
        (leaving huge empty margins); the ``<Configure>`` binding then stretches
        the inner form to the viewport so its two columns split the full width.
        Harmless on StatusWindow, whose container already fills its window.
        """
        outer = tk.Frame(self.container, bg="#1a1a1a")
        outer.pack(fill="both", expand=True, pady=10)
        canvas = tk.Canvas(outer, bg="#1a1a1a", highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        form = tk.Frame(canvas, bg="#1a1a1a")
        form.grid_columnconfigure(0, weight=1, uniform="mw")
        form.grid_columnconfigure(1, weight=1, uniform="mw")
        form.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        self._mw_form_window = canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(self._mw_form_window, width=e.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        top = self.container.winfo_toplevel()
        top.update_idletasks()
        canvas.configure(
            width=int(top.winfo_width() * 0.9),
            height=int(top.winfo_height() * 0.7),
        )
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
        self._mw_vars["start_time"] = self._mw_entry(form, "Start time (HH:MM):")
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
        self._mw_tt_frame = tk.Frame(form, bg="#1a1a1a")
        self._mw_other_frame = tk.Frame(form, bg="#1a1a1a")
        for sport_frame in (self._mw_tt_frame, self._mw_other_frame):
            sport_frame.grid_columnconfigure(0, weight=1, uniform="mwact")
            sport_frame.grid_columnconfigure(1, weight=1, uniform="mwact")
            sport_frame.grid(
                row=act_row, column=0, columnspan=2, sticky="ew", padx=12, pady=6
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

        self._mw_error_label = self._text("", color="#ff4444", pady=5)
        button_row = self._button_row()
        self._button(
            button_row,
            "SUBMIT",
            bg="#0066cc",
            command=self._submit_manual_workout_form,
            width=12,
        ).pack(side="left", padx=10)
        self._button(
            button_row,
            "BACK",
            bg="#aa0000",
            command=self._on_manual_workout_cancelled,
            width=12,
        ).pack(side="left", padx=10)

    def _mw_sport_row(self, parent: tk.Widget) -> None:
        """Add the sport-selector dropdown; swaps the activity-details section."""
        self._mw_sport_var = tk.StringVar(
            value=_manual_workout.SPORT_LABELS[_manual_workout.SPORT_TABLE_TENNIS]
        )
        row = tk.Frame(parent, bg="#1a1a1a")
        tk.Label(
            row,
            text="Sport:",
            font=("Arial", 16),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=5)
        tk.OptionMenu(
            row,
            self._mw_sport_var,
            *_manual_workout.SPORT_LABELS.values(),
            command=self._on_mw_sport_changed,
        ).pack(side="left", padx=5)
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
        except (tk.TclError, ValueError):
            return 0

    def _submit_manual_workout_form(self) -> None:
        """Validate the form and either show an error or save + notify host."""
        try:
            rpe = int(self._mw_rpe_var.get())
        except (tk.TclError, ValueError):
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
        record_pc_manual(self.log_file, entry)
        self._on_manual_workout_saved(entry)
