"""One-word hover tooltips for glyph-only Tk buttons (textgate tooltip exception).

kuhy allows ONE word naming what an icon means, shown only on hover. The tip
is a Label placed inside the button's own window on <Enter> and destroyed on
<Leave> or a click, so no screen paints it until the pointer is on the button.

Not a Toplevel: on a lock surface gatelock's recovery tick disowns any popup
window within a second (see tests/test_no_popup_widgets.py), so the tip has
to live in the same window as the button it names.
"""

from __future__ import annotations

import tkinter as tk

from screen_locker import _glyphs as g

_OFFSET = 16  # px below-right of the pointer, so the tip never covers it


def tooltip_word(glyph_text: str) -> str | None:
    """Return the hover word for a button's glyph text, or None to skip it."""
    return g.TOOLTIP.get(glyph_text)


def attach_tooltip(widget: tk.Widget, word: str) -> None:
    """Show ``word`` beside the pointer while it hovers ``widget``."""
    tip: list[tk.Label] = []

    def show(event: tk.Event) -> None:
        hide(event)
        window = widget.winfo_toplevel()
        label = tk.Label(window, text=word)
        label.place(
            x=event.x_root - window.winfo_rootx() + _OFFSET,
            y=event.y_root - window.winfo_rooty() + _OFFSET,
        )
        label.lift()
        tip.append(label)

    def hide(_event: tk.Event) -> None:
        while tip:
            tip.pop().destroy()

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<ButtonPress>", hide, add="+")
