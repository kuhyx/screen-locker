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

from gatelock import escape_text_tab_trap

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
            padx=self._colors.space("sm"),
            # "xs", not "sm": with ten cells plus headings this gap is paid
            # per row, and the form has to fit a 768px panel in full.
            pady=self._colors.space("xs"),
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
            font=self._colors.font("body", bold=True),
            fg=self._colors.accent,
            bg=self._colors.bg,
            anchor="w",
        )
        self._mw_grid(parent, label, full=True)

    def _mw_entry(
        self, parent: tk.Widget, label: str, *, focus: bool = False
    ) -> tk.StringVar:
        """Add a half-width label+entry cell and return its backing StringVar.

        Builds its own cell inline (rather than reusing ``_add_label_entry``,
        which is pack-based and shared with the sick dialog) so it slots into
        the two-column grid. Paste stays disabled via ``disable_paste``.

        Args:
            parent: The grid master to place the cell in.
            label: Text shown above the entry.
            focus: Give this entry the keyboard focus; see
                ``_ui_widgets.UIWidgetsMixin._add_label_entry`` for why exactly
                one field per form should ask.
        """
        var = tk.StringVar()
        cell = tk.Frame(parent, bg=self._colors.bg)
        # Label beside the field, not above it. Stacked, each of the ten cells
        # cost two lines plus the gap between them, and the form measured
        # 1320px against a 768px panel; side-by-side each cell is one line
        # tall. The lock cannot scroll its way out of not fitting, so rows this
        # form does not need are rows it must not spend.
        tk.Label(
            cell,
            text=label,
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
            anchor="w",
        ).pack(side="left", padx=(0, self._colors.space("xs")))
        entry = tk.Entry(
            cell,
            textvariable=var,
            font=self._colors.font("label"),
            bg=self._colors.field_bg,
            fg=self._colors.fg,
            insertbackground=self._colors.fg,
            **self._colors.focus_kwargs(),
        )
        entry.pack(side="left", fill="x", expand=True)
        disable_paste(entry)
        if focus:
            entry.focus_set()
        self._mw_grid(parent, cell)
        return var

    def _mw_int_field(
        self, parent: tk.Widget, label: str, *, frm: int = 0, to: int = 99
    ) -> tk.IntVar:
        """Add a half-width label + numeric Spinbox and return its IntVar."""
        var = tk.IntVar(value=0)
        row = tk.Frame(parent, bg=self._colors.bg)
        tk.Label(
            row,
            text=label,
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
        ).pack(side="left", padx=self._colors.space("xs"))
        tk.Spinbox(
            row,
            from_=frm,
            to=to,
            textvariable=var,
            width=4,
            font=self._colors.font("label"),
            **self._colors.focus_kwargs(),
        ).pack(side="left", padx=self._colors.space("xs"))
        self._mw_grid(parent, row)
        return var

    def _mw_textbox(self, parent: tk.Widget, label: str) -> tk.Text:
        """Add a half-width label + multi-line Text cell and return the widget.

        Half-width, not full: three full-width reflection boxes were three
        whole rows of a form that has to fit a 768px panel, and two of them
        sit side by side just as legibly.
        """
        cell = tk.Frame(parent, bg=self._colors.bg)
        tk.Label(
            cell,
            text=label,
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
            anchor="w",
        ).pack(fill="x")
        text_widget = tk.Text(
            cell,
            height=2,
            font=self._colors.font("label"),
            bg=self._colors.field_bg,
            fg=self._colors.fg,
            insertbackground=self._colors.fg,
            **self._colors.focus_kwargs(),
        )
        text_widget.pack(pady=self._colors.space("xs"), fill="x")
        disable_paste(text_widget)
        # Tk makes <Tab> insert a literal tab and refocus the widget, and binds
        # <Shift-Tab> to nothing, so an untreated Text is a keyboard dead end --
        # and the only exits (Ctrl+Tab / Ctrl+Shift+Tab) are advertised nowhere.
        # On this form that means never reaching SUBMIT.
        escape_text_tab_trap(text_widget)
        self._mw_grid(parent, cell)
        return text_widget

    def _mw_rpe_row(self, parent: tk.Widget) -> None:
        """Add the RPE (rate of perceived exertion) spinbox row."""
        row = tk.Frame(parent, bg=self._colors.bg)
        tk.Label(
            row,
            text=(
                f"RPE — perceived exertion "
                f"({MANUAL_WORKOUT_RPE_MIN}-{MANUAL_WORKOUT_RPE_MAX}):"
            ),
            font=self._colors.font("label"),
            fg=self._colors.fg,
            bg=self._colors.bg,
        ).pack(side="left", padx=self._colors.space("xs"))
        tk.Spinbox(
            row,
            from_=MANUAL_WORKOUT_RPE_MIN,
            to=MANUAL_WORKOUT_RPE_MAX,
            textvariable=self._mw_rpe_var,
            width=4,
            font=self._colors.font("label"),
            **self._colors.focus_kwargs(),
        ).pack(side="left", padx=self._colors.space("xs"))
        self._mw_grid(parent, row)
