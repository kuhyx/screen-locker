"""Low-level widget/grid builders for the manual-workout evidence form.

Split out of ``_manual_workout_dialog`` so the dialog module stays under the
repo's file-length cap. These helpers build individual form cells and place
them into a two-column grid; the orchestration (which fields, in what order,
and submission) lives in ``ManualWorkoutDialogMixin``, which inherits this.

The host is expected to have initialised ``self._mw_grid_counters`` (per-master
grid cursors) and, for ``_mw_rpe_row``, ``self._mw_rpe_var``.
"""

from __future__ import annotations

import tkinter as tk

from screen_locker._constants import (
    MANUAL_WORKOUT_RPE_MAX,
    MANUAL_WORKOUT_RPE_MIN,
)
from screen_locker._ui_widgets import disable_paste


class ManualWorkoutFormWidgetsMixin:
    """Two-column grid placement + individual field-cell builders."""

    def _mw_grid(
        self, parent: tk.Widget, widget: tk.Widget, *, full: bool = False
    ) -> None:
        """Place ``widget`` into ``parent``'s two-column grid cursor.

        A half-width item (``full=False``) fills the next cell (left, then
        right); a ``full`` item starts a fresh row and spans both columns. Each
        master keeps its own cursor (keyed by ``id(parent)``) so nested sport
        frames grid independently of the main form.
        """
        counters = self._mw_grid_counters
        idx = counters.get(id(parent), 0)
        if full and idx % 2 == 1:
            idx += 1  # a full-width item can't share a row — bump to a new one
        row, col = divmod(idx, 2)
        widget.grid(
            row=row,
            column=col,
            columnspan=2 if full else 1,
            sticky="ew",
            padx=12,
            pady=6,
        )
        counters[id(parent)] = idx + (2 if full else 1)

    def _mw_next_full_row(self, parent: tk.Widget) -> int:
        """Reserve a fresh full-width row for a manually-gridded widget.

        Used for the twin sport frames, which share one slot and are gridded
        directly (not through ``_mw_grid``); this advances the cursor past that
        row so following fields resume cleanly.
        """
        counters = self._mw_grid_counters
        idx = counters.get(id(parent), 0)
        if idx % 2 == 1:
            idx += 1
        counters[id(parent)] = idx + 2
        return idx // 2

    def _mw_section(self, parent: tk.Widget, title: str) -> None:
        """Add a full-width section heading inside the form."""
        label = tk.Label(
            parent,
            text=title,
            font=("Arial", 20, "bold"),
            fg="#88ccff",
            bg="#1a1a1a",
            anchor="w",
        )
        self._mw_grid(parent, label, full=True)

    def _mw_entry(self, parent: tk.Widget, label: str) -> tk.StringVar:
        """Add a half-width label+entry cell and return its backing StringVar.

        Builds its own cell inline (rather than reusing ``_add_label_entry``,
        which is pack-based and shared with the sick dialog) so it slots into
        the two-column grid. Paste stays disabled via ``disable_paste``.
        """
        var = tk.StringVar()
        cell = tk.Frame(parent, bg="#1a1a1a")
        tk.Label(
            cell,
            text=label,
            font=("Arial", 16),
            fg="white",
            bg="#1a1a1a",
            anchor="w",
        ).pack(fill="x")
        entry = tk.Entry(
            cell,
            textvariable=var,
            font=("Arial", 18),
            bg="#2a2a2a",
            fg="white",
            insertbackground="white",
        )
        entry.pack(fill="x", pady=2)
        disable_paste(entry)
        self._mw_grid(parent, cell)
        return var

    def _mw_int_field(
        self, parent: tk.Widget, label: str, *, frm: int = 0, to: int = 99
    ) -> tk.IntVar:
        """Add a half-width label + numeric Spinbox and return its IntVar."""
        var = tk.IntVar(value=0)
        row = tk.Frame(parent, bg="#1a1a1a")
        tk.Label(
            row,
            text=label,
            font=("Arial", 16),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=5)
        tk.Spinbox(
            row,
            from_=frm,
            to=to,
            textvariable=var,
            width=4,
            font=("Arial", 16),
        ).pack(side="left", padx=5)
        self._mw_grid(parent, row)
        return var

    def _mw_textbox(self, parent: tk.Widget, label: str) -> tk.Text:
        """Add a full-width label + multi-line Text cell and return the widget."""
        cell = tk.Frame(parent, bg="#1a1a1a")
        tk.Label(
            cell,
            text=label,
            font=("Arial", 16),
            fg="white",
            bg="#1a1a1a",
            anchor="w",
        ).pack(fill="x", pady=(5, 0))
        text_widget = tk.Text(
            cell,
            height=3,
            font=("Arial", 14),
            bg="#2a2a2a",
            fg="white",
            insertbackground="white",
        )
        text_widget.pack(pady=2, fill="x")
        disable_paste(text_widget)
        self._mw_grid(parent, cell, full=True)
        return text_widget

    def _mw_rpe_row(self, parent: tk.Widget) -> None:
        """Add the RPE (rate of perceived exertion) spinbox row."""
        row = tk.Frame(parent, bg="#1a1a1a")
        tk.Label(
            row,
            text=(
                f"RPE — perceived exertion "
                f"({MANUAL_WORKOUT_RPE_MIN}-{MANUAL_WORKOUT_RPE_MAX}):"
            ),
            font=("Arial", 16),
            fg="white",
            bg="#1a1a1a",
        ).pack(side="left", padx=5)
        tk.Spinbox(
            row,
            from_=MANUAL_WORKOUT_RPE_MIN,
            to=MANUAL_WORKOUT_RPE_MAX,
            textvariable=self._mw_rpe_var,
            width=4,
            font=("Arial", 16),
        ).pack(side="left", padx=5)
        self._mw_grid(parent, row)
