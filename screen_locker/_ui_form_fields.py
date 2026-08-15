"""Labelled form fields and initial focus, shared by every lock surface.

Split out of :mod:`screen_locker._ui_widgets` to keep every file under the
250-line cap. Composed back into ``UIWidgetsMixin`` there, so every host
class keeps the same surface.

Each helper builds its widget on *every* monitor (the lock spans them all),
which is why they return groups rather than single widgets.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import escape_text_tab_trap

if TYPE_CHECKING:
    from screen_locker._surface_group import FrameGroup, WidgetGroup


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
    """Labelled entry/text fields and initial focus for the lock surfaces."""

    def _add_label_entry(
        self,
        parent: FrameGroup,
        *,
        label: str,
        variable: tk.StringVar,
        focus: bool = False,
    ) -> None:
        """Add a label + single-line entry pair on every monitor.

        All copies share one ``variable``, so typing on any screen is the
        same text everywhere and reading it back needs no idea which monitor
        the user actually used.

        ``focus`` gives the primary surface's copy the keyboard focus. Exactly
        one field per screen should ask: the lock takes a global grab, so with
        nothing focused the user's typing goes nowhere and there is no other
        window on screen to make that obvious.
        """
        row = parent.child_frame(bg=self._colors.bg)
        row.pack(pady=self._colors.space("sm"), fill="x")
        row.child_widgets(
            tk.Label,
            text=label,
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
            anchor="w",
        ).pack(side="top", anchor="w")
        entries = row.child_widgets(
            tk.Entry,
            textvariable=variable,
            width=50,
            font=self._colors.font("label"),
            bg=self._colors.field_bg,
            fg=self._colors.fg,
            insertbackground=self._colors.fg,
            **self._colors.focus_kwargs(),
        )
        entries.pack(side="top", anchor="w", pady=self._colors.space("xs"))
        for entry in entries:
            disable_paste(entry)
        if focus:
            entries.first.focus_set()

    def _add_label_text(
        self,
        parent: FrameGroup,
        *,
        label: str,
        height: int = 4,
    ) -> WidgetGroup:
        """Add a label + multi-line ``Text`` pair on every monitor.

        Use this instead of building a bare ``tk.Text``: it un-traps Tab.
        Tk makes ``<Tab>`` insert a literal tab and refocus the widget, and
        binds ``<Shift-Tab>`` to nothing, so an untreated multi-line field is a
        keyboard dead end whose only exits (``Ctrl+Tab``/``Ctrl+Shift+Tab``) are
        not advertised anywhere. On a lock surface that means a user who tabs
        into it can never reach the submit button.
        """
        row = parent.child_frame(bg=self._colors.bg)
        row.pack(pady=self._colors.space("sm"), fill="x")
        row.child_widgets(
            tk.Label,
            text=label,
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
            anchor="w",
        ).pack(side="top", anchor="w")
        boxes = row.child_widgets(
            tk.Text,
            width=60,
            height=height,
            wrap="word",
            font=self._colors.font("label"),
            bg=self._colors.field_bg,
            fg=self._colors.fg,
            insertbackground=self._colors.fg,
            **self._colors.focus_kwargs(),
        )
        boxes.pack(side="top", anchor="w", pady=self._colors.space("xs"))
        for box in boxes:
            disable_paste(box)
            escape_text_tab_trap(box)
        return boxes

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
