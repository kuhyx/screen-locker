"""Sick-day justification + commitment dialog mixin for the screen locker."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import escape_text_tab_trap

from screen_locker import _sick_tracker
from screen_locker._constants import (
    SICK_COMMITMENT_FORCED_READ_SECONDS,
    SICK_JUSTIFICATION_MIN_CHARS,
)
from screen_locker._sick_commitment import SickCommitmentMixin
from screen_locker._surface_group import FrameGroup, TextGroup
from screen_locker._ui_widgets import disable_paste as _disable_paste

if TYPE_CHECKING:
    from screen_locker._sick_tracker import SickHistory

_logger = logging.getLogger(__name__)


class SickDialogMixin(SickCommitmentMixin):
    """Renders the sick-day justification screen and commitment prompts."""

    # ------------------------------------------------------------------
    # Sick-day justification dialog
    # ------------------------------------------------------------------

    def _show_sick_justification(self) -> None:
        """Render the structured sick-day justification screen."""
        history = _sick_tracker.load_history()
        self._sick_history_cache: SickHistory = history
        self.clear_container()
        self._label("Sick Day Request", color=self._colors.warning, pad="sm")
        self._text(_sick_tracker.budget_summary(history), color=self._colors.warning)

        recent = _sick_tracker.format_recent_justifications(history)
        if recent:
            self._text(
                "Recent sick days:", role="label", color=self._colors.muted, pad="sm"
            )
            self._text(recent, role="label", color=self._colors.muted, pad="sm")

        had_commitment = _sick_tracker.had_commitment_for_today(history)
        if had_commitment:
            self._text(
                "⚠ Yesterday you committed to working out today.",
                role="body",
                color=self._colors.danger,
            )
            self._text(
                "Breaking the commitment costs 2 sick-budget days.",
                role="label",
                color=self._colors.danger,
            )

        self._build_justification_form(had_commitment=had_commitment)

    def _build_justification_form(self, *, had_commitment: bool) -> None:
        """Add justification form fields and submit button to the container."""
        form = self.container.child_frame(bg=self._colors.bg)
        form.pack(pady=self._colors.space("sm"))

        self._sick_symptom_var = tk.StringVar()
        self._sick_onset_var = tk.StringVar()
        self._sick_severity_var = tk.IntVar(value=5)
        self._sick_text_widget = self._add_form_widgets(form)

        self._sick_error_label = self._text("", color=self._colors.danger, pad="sm")

        button_row = self._button_row()
        # Starts disabled during the forced-read delay -- field_bg (our
        # neutral/secondary token) signals "not yet actionable" better than
        # the accent used for an immediately-clickable submit.
        self._sick_submit_button = self._button(
            button_row,
            "SUBMIT",
            bg=self._colors.field_bg,
            command=self._submit_sick_justification,
            width=12,
        )
        self._sick_submit_button.pack(side="left", padx=self._colors.space("sm"))
        self._button(
            button_row,
            "BACK",
            bg=self._colors.field_bg,
            command=self._start_phone_check,
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))

        if had_commitment:
            self._sick_submit_button.config(state="disabled")
            self._commitment_forced_remaining = SICK_COMMITMENT_FORCED_READ_SECONDS
            self._update_commitment_forced_delay()

    def _add_form_widgets(self, parent: FrameGroup) -> TextGroup:
        """Create symptom/onset/severity/text widgets. Returns the text widget."""
        self._add_label_entry(
            parent,
            label="Symptom (e.g. fever, nausea):",
            variable=self._sick_symptom_var,
            focus=True,
        )
        self._add_label_entry(
            parent,
            label="When did it start? (e.g. last night):",
            variable=self._sick_onset_var,
        )
        sev_row = parent.child_frame(bg=self._colors.bg)
        sev_row.pack(pady=self._colors.space("sm"))
        sev_row.child_widgets(
            tk.Label,
            text="Severity (1-10):",
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
        ).pack(side="left", padx=self._colors.space("xs"))
        sev_row.child_widgets(
            tk.Spinbox,
            from_=1,
            to=10,
            textvariable=self._sick_severity_var,
            width=4,
            font=self._colors.font("label"),
        ).pack(side="left", padx=self._colors.space("xs"))

        parent.child_widgets(
            tk.Label,
            text=(f"Describe how you feel (min {SICK_JUSTIFICATION_MIN_CHARS} chars):"),
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
        ).pack(pady=self._colors.space("sm"))
        text_widgets = TextGroup(
            list(
                parent.child_widgets(
                    tk.Text,
                    width=60,
                    height=6,
                    font=self._colors.font("label"),
                    bg=self._colors.field_bg,
                    fg=self._colors.fg,
                    insertbackground=self._colors.fg,
                    **self._colors.focus_kwargs(),
                )
            )
        )
        text_widgets.pack(pady=self._colors.space("sm"))
        for text_widget in text_widgets:
            _disable_paste(text_widget)
            # Tk traps <Tab> inside a Text (inserts a tab, refocuses itself) and
            # no-ops <Shift-Tab>, so without this a keyboard-only user who tabs
            # into the justification box can never reach SUBMIT -- inside a lock
            # whose only other exit is waiting out the countdown.
            escape_text_tab_trap(text_widget)
        return text_widgets

    def _update_commitment_forced_delay(self) -> None:
        """Tick down the forced-read delay then enable the submit button."""
        if self._commitment_forced_remaining > 0:
            self._sick_submit_button.config(
                text=f"WAIT {self._commitment_forced_remaining}s",
            )
            self._commitment_forced_remaining -= 1
            self.root.after(1000, self._update_commitment_forced_delay)
        else:
            self._sick_submit_button.config(text="SUBMIT", state="normal")

    def _submit_sick_justification(self) -> None:
        """Validate the form and either show an error or proceed to countdown."""
        symptom = self._sick_symptom_var.get()
        onset = self._sick_onset_var.get()
        try:
            severity = int(self._sick_severity_var.get())
        except (tk.TclError, ValueError) as exc:
            _logger.warning(
                "Sick-day severity is not an integer (%s) — submitting it as 0, "
                "which the justification validator will reject",
                exc,
            )
            severity = 0
        text = self._sick_text_widget.get("1.0", "end").strip()
        draft = _sick_tracker.JustificationDraft(
            symptom=symptom,
            onset=onset,
            severity=severity,
            text=text,
        )
        error = _sick_tracker.validate_justification(draft)
        if error is not None:
            self._sick_error_label.config(text=error)
            return

        history = self._sick_history_cache
        _sick_tracker.add_justification(history, draft)
        if not _sick_tracker.save_history(history):
            self._sick_error_label.config(
                text="Could not persist sick history — try again",
            )
            return
        self._proceed_to_sick_countdown()

    # ------------------------------------------------------------------
    # Commitment prompt (after a verified workout)
    # ------------------------------------------------------------------
