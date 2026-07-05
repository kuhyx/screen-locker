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
    MANUAL_WORKOUT_RPE_MAX,
    MANUAL_WORKOUT_RPE_MIN,
)
from screen_locker._ui_widgets import disable_paste

_logger = logging.getLogger(__name__)

_SPORT_LABEL_TO_CODE = {
    label: code for code, label in _manual_workout.SPORT_LABELS.items()
}


class ManualWorkoutDialogMixin:
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

    def _build_manual_workout_form(self) -> None:
        """Build the scrollable evidence form and submit/back buttons."""
        outer = tk.Frame(self.container, bg="#1a1a1a")
        outer.pack(fill="both", expand=True, pady=10)
        canvas = tk.Canvas(outer, bg="#1a1a1a", highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        form = tk.Frame(canvas, bg="#1a1a1a")
        form.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

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
        self._mw_vars["location_maps_link"] = self._mw_entry(
            form,
            "Google Maps link (optional — easier to fill from your phone):",
        )
        self._mw_vars["transport_method"] = self._mw_entry(
            form, "How did you get there?"
        )
        self._mw_vars["cost"] = self._mw_entry(form, "Cost (e.g. 40 PLN):")
        self._mw_vars["reservation_phone"] = self._mw_entry(
            form, "Reservation phone number (if booked by phone, optional):"
        )

        self._mw_section(form, "Evidence")
        self._mw_vars["proof_screenshot_path"] = self._mw_entry(
            form,
            "Screenshot path as proof of arrangement "
            "(optional — phone-oriented field):",
        )

        self._mw_section(form, "Activity details")
        self._mw_tt_frame = tk.Frame(form, bg="#1a1a1a")
        self._mw_other_frame = tk.Frame(form, bg="#1a1a1a")
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

    def _mw_section(self, parent: tk.Widget, title: str) -> None:
        """Add a section heading inside the form."""
        tk.Label(
            parent,
            text=title,
            font=("Arial", 16, "bold"),
            fg="#88ccff",
            bg="#1a1a1a",
            anchor="w",
        ).pack(fill="x", pady=(15, 2))

    def _mw_sport_row(self, parent: tk.Widget) -> None:
        """Add the sport-selector dropdown; swaps the activity-details section."""
        self._mw_sport_var = tk.StringVar(
            value=_manual_workout.SPORT_LABELS[_manual_workout.SPORT_TABLE_TENNIS]
        )
        row = tk.Frame(parent, bg="#1a1a1a")
        row.pack(pady=5, fill="x")
        tk.Label(
            row,
            text="Sport:",
            font=("Arial", 14),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=5)
        tk.OptionMenu(
            row,
            self._mw_sport_var,
            *_manual_workout.SPORT_LABELS.values(),
            command=self._on_mw_sport_changed,
        ).pack(side="left", padx=5)

    def _on_mw_sport_changed(self, selected_label: str) -> None:
        """Show the fields for the newly-selected sport, hide the other's."""
        sport = _SPORT_LABEL_TO_CODE.get(
            selected_label, _manual_workout.SPORT_TABLE_TENNIS
        )
        if sport == _manual_workout.SPORT_TABLE_TENNIS:
            self._mw_other_frame.pack_forget()
            self._mw_tt_frame.pack(fill="x")
        else:
            self._mw_tt_frame.pack_forget()
            self._mw_other_frame.pack(fill="x")

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

    def _mw_entry(self, parent: tk.Widget, label: str) -> tk.StringVar:
        """Add a label+entry field and return its backing StringVar."""
        var = tk.StringVar()
        self._add_label_entry(parent, label=label, variable=var)
        return var

    def _mw_int_field(
        self, parent: tk.Widget, label: str, *, frm: int = 0, to: int = 99
    ) -> tk.IntVar:
        """Add a label + numeric Spinbox field and return its backing IntVar."""
        var = tk.IntVar(value=0)
        row = tk.Frame(parent, bg="#1a1a1a")
        row.pack(pady=5, fill="x")
        tk.Label(
            row,
            text=label,
            font=("Arial", 14),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=5)
        tk.Spinbox(
            row,
            from_=frm,
            to=to,
            textvariable=var,
            width=4,
            font=("Arial", 14),
        ).pack(side="left", padx=5)
        return var

    def _mw_textbox(self, parent: tk.Widget, label: str) -> tk.Text:
        """Add a label + multi-line Text field and return the widget."""
        tk.Label(
            parent,
            text=label,
            font=("Arial", 14),
            fg="white",
            bg="#1a1a1a",
            anchor="w",
        ).pack(fill="x", pady=(5, 0))
        text_widget = tk.Text(
            parent,
            width=60,
            height=4,
            font=("Arial", 12),
            bg="#2a2a2a",
            fg="white",
            insertbackground="white",
        )
        text_widget.pack(pady=2, fill="x")
        disable_paste(text_widget)
        return text_widget

    def _mw_rpe_row(self, parent: tk.Widget) -> None:
        """Add the RPE (rate of perceived exertion) spinbox row."""
        row = tk.Frame(parent, bg="#1a1a1a")
        row.pack(pady=5, fill="x")
        tk.Label(
            row,
            text=(
                f"RPE — perceived exertion "
                f"({MANUAL_WORKOUT_RPE_MIN}-{MANUAL_WORKOUT_RPE_MAX}):"
            ),
            font=("Arial", 14),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=5)
        tk.Spinbox(
            row,
            from_=MANUAL_WORKOUT_RPE_MIN,
            to=MANUAL_WORKOUT_RPE_MAX,
            textvariable=self._mw_rpe_var,
            width=4,
            font=("Arial", 14),
        ).pack(side="left", padx=5)

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
            location_maps_link=self._mw_vars["location_maps_link"].get(),
            reservation_phone=self._mw_vars["reservation_phone"].get(),
            proof_screenshot_path=self._mw_vars["proof_screenshot_path"].get(),
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
        self._on_manual_workout_saved(entry)
