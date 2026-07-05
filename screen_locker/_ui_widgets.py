"""UI widget helper methods mixin for the screen locker."""

from __future__ import annotations

import contextlib
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


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
        """Remove all widgets from the main container."""
        for widget in self.container.winfo_children():
            widget.destroy()

    def _label(
        self,
        text: str,
        *,
        font_size: int = 36,
        color: str = "white",
        pady: int = 20,
    ) -> tk.Label:
        """Create and pack a bold label in the container."""
        label = tk.Label(
            self.container,
            text=text,
            font=("Arial", font_size, "bold"),
            fg=color,
            bg="#1a1a1a",
        )
        label.pack(pady=pady)
        return label

    def _text(
        self,
        text: str,
        *,
        font_size: int = 18,
        color: str = "white",
        pady: int = 10,
    ) -> tk.Label:
        """Create and pack a non-bold text label in the container."""
        label = tk.Label(
            self.container,
            text=text,
            font=("Arial", font_size),
            fg=color,
            bg="#1a1a1a",
        )
        label.pack(pady=pady)
        return label

    def _button(
        self,
        parent: tk.Widget,
        text: str,
        *,
        bg: str,
        command: Callable[[], None],
        width: int = 10,
    ) -> tk.Button:
        """Create a styled button (caller must pack)."""
        return tk.Button(
            parent,
            text=text,
            font=("Arial", 24, "bold"),
            bg=bg,
            fg="white",
            width=width,
            command=command,
            cursor="hand2" if self.demo_mode else "",
        )

    def _button_row(self) -> tk.Frame:
        """Create and pack a horizontal button container."""
        frame = tk.Frame(self.container, bg="#1a1a1a")
        frame.pack(pady=20)
        return frame

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
        disable_paste(entry)
