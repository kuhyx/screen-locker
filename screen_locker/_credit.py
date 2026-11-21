"""kuhy's shared credit logo on screen-locker's Tk windows.

kuhy, 2026-11-21: the logo goes "everywhere in every single app, desktop
program", lockers too (``kuhy_credit`` README, kuhyx/utils). The widget is
the shared ``kuhy_credit.tk.KuhyCredit``; this module only fixes where it
sits so every window puts it in the same corner. A click on its panel opens
the site in a browser tab, which stays behind the fullscreen lock until the
lock closes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kuhy_credit.tk import KuhyCredit

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import LockConfig


def place_credit(parent: tk.Misc, config: LockConfig) -> KuhyCredit:
    """Place the logo in ``parent``'s bottom-right corner, above its siblings.

    ``parent`` must be the toplevel (a lock surface or a plain window), never
    a content frame a flow clears and repaints. Call it after the window's
    full-size viewport exists: siblings stack in creation order, so the logo
    lands above it. (``KuhyCredit.lift`` is a Canvas item raise, not a
    window raise, so it cannot do this.)
    """
    pad = config.space("xl")
    credit = KuhyCredit(parent, theme="dark", size=config.type_px("display"))
    credit.place(relx=1, rely=1, x=-pad, y=-pad, anchor="se")
    return credit
