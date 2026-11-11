#!/usr/bin/env python3
"""Assert no locker screen paints a word (textgate: zero visible text).

kuhy's rule: anything he sees carries no text unless he asked for it. The
``textgate scan`` only sees string literals passed to known keywords, so it
misses every ``self._label("...")`` / ``self._text(f"...")`` call -- the
whole locker UI. This check paints every screen for real (Xvfb, the same
``ScreenHost`` the fit check uses), walks the widget tree, and fails on any
2+ letter word that is not content (see ``_text_free_rules``).

    cd ~/src/screen-locker && python3 -m scripts.verify_text_free [--shots DIR]

``--shots DIR`` also saves one PNG per screen (ImageMagick ``import``), so
the same run is the before/after evidence.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from types import SimpleNamespace

from scripts._fit_extra_screens import EXTRA_SCREENS
from scripts._text_free_rules import words_in
from scripts._text_free_screens import extra_paints
from scripts._xvfb_reexec import reexec_under_xvfb
from scripts.verify_screen_fits import SCREENS, ScreenHost

_logger = logging.getLogger(__name__)

INNER_ENV = "_TEXT_FREE_CHECK_INNER"
_SIZE = (1366, 768)
_TYPED = frozenset({"Entry", "Spinbox", "Text", "TEntry", "TSpinbox", "TCombobox"})


def _widget_texts(widget: tk.Misc) -> list[str]:
    """Every painted string under *widget*: label/button text and menus."""
    out: list[str] = []
    for child in widget.winfo_children():
        out += _widget_texts(child)
    # What the user typed is content. (Tk abbreviates options, so an Entry's
    # cget("text") would answer its textvariable's *name*.)
    if widget.winfo_class() in _TYPED:
        return out
    try:
        text = str(widget.cget("text"))
    except tk.TclError:
        text = ""
    try:
        var = str(widget.cget("textvariable"))
    except tk.TclError:
        var = ""
    if var:
        text = f"{text} {widget.getvar(var)}"
    if widget.winfo_class() == "Menu":
        last = widget.index("end")
        for i in range(0 if last is None else int(last) + 1):
            try:
                text += " " + str(widget.entrycget(i, "label"))
            except tk.TclError:
                continue
    return [text, *out] if text.strip() else out


def _shoot(win: tk.Toplevel, path: Path) -> None:
    """Save *win* as a PNG; a failed shot is logged, never fatal."""
    win.update()
    result = subprocess.run(
        ["import", "-window", str(win.winfo_id()), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        _logger.warning("screenshot %s failed: %s", path, result.stderr.strip())


def _paint_all(root: tk.Tk, shots: Path | None) -> dict[str, list[str]]:
    """Paint each screen in its own window; map screen -> offending words."""
    builds = [
        (s.name, lambda surface, p=s.paint: p(ScreenHost(surface))) for s in SCREENS
    ]
    builds += [(name, build) for name, build in EXTRA_SCREENS]
    builds += extra_paints()
    bad: dict[str, list[str]] = {}
    for name, build in builds:
        win = tk.Toplevel(root)
        win.geometry(f"{_SIZE[0]}x{_SIZE[1]}")
        frame = tk.Frame(win, bg="#211D1B")
        frame.pack(fill="both", expand=True)
        build(SimpleNamespace(content=frame))
        win.update_idletasks()
        words = [w for t in _widget_texts(win) for w in words_in(t)]
        if words:
            bad[name] = words
        if shots is not None:
            _shoot(win, shots / f"{name}.png")
        win.destroy()
    return bad


def main(argv: list[str] | None = None) -> int:
    """Paint every screen; exit 1 listing each one that still shows words."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    args = sys.argv[1:] if argv is None else argv
    if os.environ.get(INNER_ENV) != "1":
        os.environ["_TEXT_FREE_ARGS"] = "\x1f".join(args)
        return reexec_under_xvfb(inner_env=INNER_ENV, module="scripts.verify_text_free")
    args = [a for a in os.environ.get("_TEXT_FREE_ARGS", "").split("\x1f") if a]
    shots = Path(args[args.index("--shots") + 1]) if "--shots" in args else None
    if shots is not None:
        shots.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    bad = _paint_all(root, shots)
    root.destroy()
    if not bad:
        _logger.info("OK: no locker screen paints a word.")
        return 0
    for name, words in bad.items():
        _logger.error("%s: %s", name, " ".join(words))
    _logger.error("%d screen(s) still paint words.", len(bad))
    return 1


if __name__ == "__main__":
    sys.exit(main())
