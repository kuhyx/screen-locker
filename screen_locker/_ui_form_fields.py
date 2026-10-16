"""Paste friction and initial focus, shared by every lock surface.

Split out of :mod:`screen_locker._ui_widgets` to keep every file under the
250-line cap. Composed back into ``UIWidgetsMixin`` there, so every host
class keeps the same surface.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screen_locker._surface_group import FrameGroup


def disable_paste(widget: tk.Widget) -> None:
    """Disable paste in a Tk Entry/Text widget.

    Friction-only: a determined user can still bypass via xdotool, but the
    point is removing the trivial Ctrl+V shortcut so the user must
    actually type their input.
    """
    for sequence in ("<<Paste>>", "<Control-v>", "<Control-V>", "<Button-2>"):
        with contextlib.suppress(tk.TclError, AttributeError):
            widget.bind(sequence, lambda _e: "break")


class UIFormFieldsMixin:
    """Initial focus for the lock surfaces."""

    def _focus_first_button(self, row: FrameGroup) -> None:
        """Give the primary surface's first button keyboard focus.

        The lock takes a global grab and there is no other window on screen, so
        a surface that starts with *nothing* focused leaves the user pressing
        keys into the void with no visible ring to hint where focus went. The
        retry screen (TRY AGAIN / I'm sick / Log Manual Workout) had exactly
        that problem, because ``on_focus_ready`` is a documented no-op.
        """
        for child in row.first.winfo_children():
            if child.winfo_class() == "Button":
                child.focus_set()
                return
