"""UI widget helper methods mixin for the screen locker."""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

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


class UIWidgetsMixin:
    """Mixin providing low-level widget creation helpers."""

    def clear_container(self) -> None:
        """Remove all widgets from the main container, on every monitor."""
        self.container.clear()

    def _label(
        self,
        text: str,
        *,
        font_size: int = 36,
        color: str | None = None,
        pady: int = 20,
    ) -> WidgetGroup:
        """Create and pack a bold label on every monitor."""
        label = self.container.child_widgets(
            tk.Label,
            text=text,
            font=(self._colors.font_family, font_size, "bold"),
            fg=color or self._colors.fg,
            bg=self._colors.bg,
        )
        label.pack(pady=pady)
        return label

    def _text(
        self,
        text: str,
        *,
        font_size: int = 18,
        color: str | None = None,
        pady: int = 10,
    ) -> WidgetGroup:
        """Create and pack a non-bold text label on every monitor."""
        label = self.container.child_widgets(
            tk.Label,
            text=text,
            font=(self._colors.font_family, font_size),
            fg=color or self._colors.fg,
            bg=self._colors.bg,
        )
        label.pack(pady=pady)
        return label

    def _fg_for(self, bg: str) -> str:
        """Return the correct label color for a widget with background `bg`.

        The four filled semantic surfaces (accent/success/warning/danger)
        all sit in the same mid-light lightness band, so `fg` (near-white,
        meant for the neutral `bg`/`field_bg` surfaces) under-contrasts on
        every one of them -- `on_fill` (dark) is required instead. Deriving
        this from `bg` means a new filled-button call site can't reintroduce
        the bug by omission.
        """
        fills = {
            self._colors.accent,
            self._colors.success,
            self._colors.warning,
            self._colors.danger,
        }
        return self._colors.on_fill if bg in fills else self._colors.fg

    def _button(
        self,
        parent: FrameGroup,
        text: str,
        *,
        bg: str,
        command: Callable[[], None],
        width: int = 10,
    ) -> WidgetGroup:
        """Create a styled button on every monitor (caller must pack).

        Every copy gets the *same* ``command``, so pressing the button on
        whichever screen the user is actually looking at does the one thing
        once -- the same trick the shared entry variable plays for typing.

        Padding follows the shared 2x horizontal:vertical ratio (rule 22);
        `relief="flat"` is the one depth technique every button in the app
        uses now (rule 27), matching what `_heat_skip.py` already did alone.
        """
        return parent.child_widgets(
            tk.Button,
            text=text,
            font=(self._colors.font_family, 24, "bold"),
            bg=bg,
            fg=self._fg_for(bg),
            width=width,
            command=command,
            cursor="hand2" if self.demo_mode else "",
            relief="flat",
            padx=24,
            pady=12,
        )

    def _button_row(self) -> FrameGroup:
        """Create and pack a horizontal button container on every monitor."""
        frame = self.container.child_frame(bg=self._colors.bg)
        frame.pack(pady=20)
        return frame

    def _add_label_entry(
        self,
        parent: FrameGroup,
        *,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        """Add a label + single-line entry pair on every monitor.

        All copies share one ``variable``, so typing on any screen is the
        same text everywhere and reading it back needs no idea which monitor
        the user actually used.
        """
        row = parent.child_frame(bg=self._colors.bg)
        row.pack(pady=8, fill="x")
        row.child_widgets(
            tk.Label,
            text=label,
            font=(self._colors.font_family, 14),
            fg=self._colors.fg,
            bg=self._colors.bg,
            anchor="w",
        ).pack(side="top", anchor="w")
        entries = row.child_widgets(
            tk.Entry,
            textvariable=variable,
            width=50,
            font=(self._colors.font_family, 14),
            bg=self._colors.field_bg,
            fg=self._colors.fg,
            insertbackground=self._colors.fg,
        )
        entries.pack(side="top", anchor="w", pady=4)
        for entry in entries:
            disable_paste(entry)
