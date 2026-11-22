"""One-word hover tooltips on the glyph buttons."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from screen_locker import _glyphs as g
from screen_locker._tooltip import attach_tooltip, tooltip_word

_WORD = re.compile(r"^[A-Za-z][A-Za-z-]{0,19}$")


def test_every_tooltip_is_one_word() -> None:
    """Every hover word is one word of at most 20 characters."""
    assert g.TOOLTIP
    for word in g.TOOLTIP.values():
        assert _WORD.match(word), word


def test_unknown_glyph_has_no_tooltip() -> None:
    """A glyph outside the map gets no tooltip; a mapped one gets its word."""
    assert tooltip_word("zzz") is None
    assert tooltip_word(g.RETRY) == "Retry"


def test_hover_shows_and_leave_hides_the_word() -> None:
    """Enter places the word inside the button's own window; Leave destroys it."""
    widget = MagicMock()
    window = widget.winfo_toplevel.return_value
    window.winfo_rootx.return_value = 4
    window.winfo_rooty.return_value = 6
    handlers = {}
    widget.bind.side_effect = lambda seq, fn, add: handlers.__setitem__(seq, fn)
    attach_tooltip(widget, "Retry")
    assert set(handlers) == {"<Enter>", "<Leave>", "<ButtonPress>"}
    event = MagicMock(x_root=10, y_root=20)
    with patch("screen_locker._tooltip.tk") as tk_mod:
        handlers["<Enter>"](event)
        label = tk_mod.Label.return_value
        tk_mod.Label.assert_called_once_with(window, text="Retry")
        label.place.assert_called_once_with(x=22, y=30)
        tk_mod.Toplevel.assert_not_called()
        handlers["<Leave>"](event)
        label.destroy.assert_called_once()
