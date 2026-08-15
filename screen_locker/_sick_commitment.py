"""The next-day commitment prompt shown after a sick day.

Split out of :mod:`screen_locker._sick_dialog` to keep every file under the
250-line cap. Composed back into ``SickDialogMixin`` there, so callers see no
change.

Taking a sick day asks for a commitment to train tomorrow; breaking it is
recorded and costs budget, which is what stops sick days being free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker import _sick_tracker
from screen_locker._constants import COMMITMENT_PROMPT_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from collections.abc import Callable


class SickCommitmentMixin:
    """Asks for, times out, and records the next-day training commitment."""

    def _show_commitment_prompt(self, *, on_done: Callable[[], None]) -> None:
        """Ask the user to commit to working out tomorrow.

        Calls ``on_done()`` once the user answers or the timeout elapses.
        """
        self.clear_container()
        self._label(
            "Commit to working out tomorrow?",
            role="display",
            color=self._colors.warning,
            pad="md",
        )
        # ~80 chars at font_size 16 would render as one unbroken line past the
        # ~70-char readable range (rule 21) -- wrap it explicitly.
        prompt = self._text(
            "If you say YES and skip via 'I'm sick' tomorrow, "
            "the sick day costs 2x normal.",
            role="body",
        )
        prompt.config(wraplength=560, justify="center")
        self._commitment_done_fn = on_done
        self._commitment_remaining = COMMITMENT_PROMPT_TIMEOUT_SECONDS
        self._commitment_timer_label = self._text(
            f"Auto-skipping in {COMMITMENT_PROMPT_TIMEOUT_SECONDS}s",
            color=self._colors.muted,
        )
        row = self._button_row()
        self._button(
            row,
            "YES",
            bg=self._colors.success,
            command=lambda: self._answer_commitment(commit=True),
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
        self._button(
            row,
            "NO",
            bg=self._colors.field_bg,
            command=lambda: self._answer_commitment(commit=False),
            width=12,
        ).pack(side="left", padx=self._colors.space("sm"))
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
