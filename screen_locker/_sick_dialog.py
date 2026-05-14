"""Sick-day justification + commitment dialog mixin for the screen locker."""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from typing import TYPE_CHECKING

from python_pkg.screen_locker import _sick_tracker
from python_pkg.screen_locker._constants import (
    COMMITMENT_PROMPT_TIMEOUT_SECONDS,
    SICK_COMMITMENT_FORCED_READ_SECONDS,
    SICK_JUSTIFICATION_MIN_CHARS,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from python_pkg.screen_locker._sick_tracker import SickHistory

_logger = logging.getLogger(__name__)


def _disable_paste(widget: tk.Widget) -> None:
    """Disable paste in a Tk Entry/Text widget.

    Friction-only: a determined user can still bypass via xdotool, but the
    point is removing the trivial Ctrl+V shortcut so the user must
    actually type their justification.
    """
    for sequence in ("<<Paste>>", "<Control-v>", "<Control-V>", "<Button-2>"):
        with contextlib.suppress(tk.TclError, AttributeError):
            widget.bind(sequence, lambda _e: "break")


class SickDialogMixin:
    """Renders the sick-day justification screen and commitment prompts."""

    # ------------------------------------------------------------------
    # Sick-day justification dialog
    # ------------------------------------------------------------------

    def _show_sick_justification(self) -> None:
        """Render the structured sick-day justification screen."""
        history = _sick_tracker.load_history()
        self._sick_history_cache: SickHistory = history
        self.clear_container()
        self._label("Sick Day Request", color="#cc6600", pady=10)
        self._text(_sick_tracker.budget_summary(history), color="#ffaa00")

        recent = _sick_tracker.format_recent_justifications(history)
        if recent:
            self._text("Recent sick days:", font_size=14, color="#888888", pady=5)
            self._text(recent, font_size=14, color="#cccccc", pady=5)

        had_commitment = _sick_tracker.had_commitment_for_today(history)
        if had_commitment:
            self._text(
                "⚠ Yesterday you committed to working out today.",
                font_size=18,
                color="#ff6666",
            )
            self._text(
                "Breaking the commitment costs 2 sick-budget days.",
                font_size=14,
                color="#ff6666",
            )

        self._build_justification_form(had_commitment=had_commitment)

    def _build_justification_form(self, *, had_commitment: bool) -> None:
        """Add justification form fields and submit button to the container."""
        form = tk.Frame(self.container, bg="#1a1a1a")
        form.pack(pady=10)

        self._sick_symptom_var = tk.StringVar()
        self._sick_onset_var = tk.StringVar()
        self._sick_severity_var = tk.IntVar(value=5)
        self._sick_text_widget = self._add_form_widgets(form)

        self._sick_error_label = self._text("", color="#ff4444", pady=5)

        button_row = self._button_row()
        self._sick_submit_button = self._button(
            button_row,
            "SUBMIT",
            bg="#666666",
            command=self._submit_sick_justification,
            width=12,
        )
        self._sick_submit_button.pack(side="left", padx=10)
        self._button(
            button_row,
            "BACK",
            bg="#aa0000",
            command=self._start_phone_check,
            width=12,
        ).pack(side="left", padx=10)

        if had_commitment:
            self._sick_submit_button.config(state="disabled")
            self._commitment_forced_remaining = SICK_COMMITMENT_FORCED_READ_SECONDS
            self._update_commitment_forced_delay()

    def _add_form_widgets(self, parent: tk.Widget) -> tk.Text:
        """Create symptom/onset/severity/text widgets. Returns the text widget."""
        self._add_label_entry(
            parent,
            label="Symptom (e.g. fever, nausea):",
            variable=self._sick_symptom_var,
        )
        self._add_label_entry(
            parent,
            label="When did it start? (e.g. last night):",
            variable=self._sick_onset_var,
        )
        sev_row = tk.Frame(parent, bg="#1a1a1a")
        sev_row.pack(pady=5)
        tk.Label(
            sev_row,
            text="Severity (1-10):",
            font=("Arial", 14),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=5)
        tk.Spinbox(
            sev_row,
            from_=1,
            to=10,
            textvariable=self._sick_severity_var,
            width=4,
            font=("Arial", 14),
        ).pack(side="left", padx=5)

        tk.Label(
            parent,
            text=(f"Describe how you feel (min {SICK_JUSTIFICATION_MIN_CHARS} chars):"),
            font=("Arial", 14),
            fg="white",
            bg="#1a1a1a",
        ).pack(pady=5)
        text_widget = tk.Text(
            parent,
            width=60,
            height=6,
            font=("Arial", 12),
            bg="#2a2a2a",
            fg="white",
            insertbackground="white",
        )
        text_widget.pack(pady=5)
        _disable_paste(text_widget)
        return text_widget

    def _add_label_entry(
        self,
        parent: tk.Widget,
        *,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        """Add a label + single-line entry pair, with paste disabled."""
        row = tk.Frame(parent, bg="#1a1a1a")
        row.pack(pady=5, fill="x")
        tk.Label(
            row,
            text=label,
            font=("Arial", 14),
            fg="white",
            bg="#1a1a1a",
            anchor="w",
        ).pack(side="top", anchor="w")
        entry = tk.Entry(
            row,
            textvariable=variable,
            width=50,
            font=("Arial", 14),
            bg="#2a2a2a",
            fg="white",
            insertbackground="white",
        )
        entry.pack(side="top", anchor="w", pady=2)
        _disable_paste(entry)

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
        except (tk.TclError, ValueError):
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

    def _show_commitment_prompt(self, *, on_done: Callable[[], None]) -> None:
        """Ask the user to commit to working out tomorrow.

        Calls ``on_done()`` once the user answers or the timeout elapses.
        """
        self.clear_container()
        self._label(
            "Commit to working out tomorrow?",
            font_size=32,
            color="#ffaa00",
            pady=20,
        )
        self._text(
            "If you say YES and skip via 'I'm sick' tomorrow, "
            "the sick day costs 2x normal.",
            font_size=16,
        )
        self._commitment_done_fn = on_done
        self._commitment_remaining = COMMITMENT_PROMPT_TIMEOUT_SECONDS
        self._commitment_timer_label = self._text(
            f"Auto-skipping in {COMMITMENT_PROMPT_TIMEOUT_SECONDS}s",
            color="#888888",
        )
        row = self._button_row()
        self._button(
            row,
            "YES",
            bg="#00aa00",
            command=lambda: self._answer_commitment(commit=True),
            width=12,
        ).pack(side="left", padx=10)
        self._button(
            row,
            "NO",
            bg="#aa0000",
            command=lambda: self._answer_commitment(commit=False),
            width=12,
        ).pack(side="left", padx=10)
        self._tick_commitment_timeout()

    def _tick_commitment_timeout(self) -> None:
        """Advance commitment auto-skip timer; default to NO when it expires."""
        if self._commitment_remaining <= 0:
            self._answer_commitment(commit=False)
            return
        self._commitment_timer_label.config(
            text=f"Auto-skipping in {self._commitment_remaining}s",
        )
        self._commitment_remaining -= 1
        self.root.after(1000, self._tick_commitment_timeout)

    def _answer_commitment(self, *, commit: bool) -> None:
        """Persist the commitment answer and call the completion callback."""
        # Disable timer re-entry by zeroing remaining.
        self._commitment_remaining = -1
        if commit:
            history = _sick_tracker.load_history()
            _sick_tracker.record_commitment_for_tomorrow(history)
            _sick_tracker.save_history(history)
        done = getattr(self, "_commitment_done_fn", None)
        if done is not None:
            self._commitment_done_fn = None
            done()
