#!/usr/bin/env python3
"""Prove the lock-screen sport selector survives gatelock's recovery tick.

``_manual_workout_dialog._mw_sport_row`` has the mechanism and the incident.
``screen_locker/tests/test_no_popup_widgets.py`` keeps popups out of the lock
path statically; this script is the *behavioural* half. It builds the real
``ManualWorkoutDialogMixin`` form with real Tk, runs gatelock's two hostile
behaviours for five ticks with the "Other" sport selected, and checks the
selection and the swapped-in fields are still there. It also re-runs the
original failure against a ``tk.OptionMenu``, so the mechanism stays
demonstrated rather than merely described -- if that check ever stops
reproducing, this harness has drifted from what gatelock actually does.

Fidelity gap, deliberate: ``HostileLock`` replays the two behaviours rather
than calling ``RecoveryLoop.tick()``, which would need a real ``SurfaceSet``
managing real per-output windows on this throwaway display. It borrows the
real ``holds_grab()`` so the predicate cannot drift; a THIRD hostile behaviour
added to ``tick()`` would not be covered here.

Not a pytest test because ``screen_locker/tests/conftest.py`` replaces the
whole ``tk`` module for every test so the suite can never reach a real
display. This script re-executes itself under Xvfb instead, so a global grab
can never freeze the developer's own session. Run it directly, or let CI:

    python3 -m scripts.verify_lock_popup_safety   # from the repo root
"""

from __future__ import annotations

import logging
import os
import sys
import tkinter as tk

from gatelock import RecoveryLoop

from scripts._popup_form_check import (
    check_real_form_survives,
    grab_holder,
    leaf,
    run_ticks,
)
from scripts._xvfb_reexec import reexec_under_xvfb

_logger = logging.getLogger(__name__)

TICK_MS = 1000
TICKS = 5
INNER_ENV = "_LOCK_POPUP_CHECK_INNER"


def check_optionmenu_still_fails() -> bool:
    """Show the original mechanism: a posted menu gets covered by the lift."""
    root = tk.Tk()
    root.geometry("800x600+0+0")
    surface = tk.Toplevel(root)
    surface.overrideredirect(boolean=True)
    surface.geometry("800x600+0+0")
    var = tk.StringVar(value="Table tennis")
    option = tk.OptionMenu(surface, var, "Table tennis", "Other")
    option.pack()
    root.update()

    menu = surface.nametowidget(option["menu"])

    def open_menu() -> None:
        menu.tk_popup(100, 100)
        root.update()

    def judge() -> bool:
        """A click where the menu appears must no longer reach the menu."""
        centre_x = menu.winfo_rootx() + menu.winfo_width() // 2
        centre_y = menu.winfo_rooty() + menu.winfo_height() // 2
        hit = root.winfo_containing(centre_x, centre_y)
        _logger.info(
            "  OptionMenu after %d ticks: grab=%s click_lands_on=%s",
            TICKS,
            grab_holder(root),
            leaf(hit),
        )
        return hit is not menu

    return run_ticks(root, judge, setup=open_menu)


def main() -> int:
    """Run both checks under Xvfb and report which held."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if os.environ.get(INNER_ENV) != "1":
        return reexec_under_xvfb(
            inner_env=INNER_ENV, module="scripts.verify_lock_popup_safety"
        )

    if not hasattr(RecoveryLoop, "holds_grab"):
        _logger.error(
            "The installed gatelock has no RecoveryLoop.holds_grab, so this "
            "check cannot replay the real grab predicate. Bump the gatelock "
            "pin in requirements.txt to a version that has it."
        )
        return 1

    _logger.info("The mechanism (a popup on a lock surface):")
    mechanism_reproduced = check_optionmenu_still_fails()
    _logger.info("The fix (radio buttons in the production form):")
    fix_holds = check_real_form_survives()

    if not mechanism_reproduced:
        _logger.error(
            "The OptionMenu was NOT covered by the recovery tick. This check no "
            "longer reproduces the failure it exists to guard against -- either "
            "gatelock stopped lifting its surfaces, or this harness has drifted."
        )
    if not fix_holds:
        _logger.error(
            "The production sport selector did NOT survive %d recovery ticks. "
            "The 2026-07-26 lock-screen bug is back.",
            TICKS,
        )
    if mechanism_reproduced and fix_holds:
        _logger.info(
            "\nOK: a popup still dies under the tick; the shipped radio-button "
            "selector survives it."
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
