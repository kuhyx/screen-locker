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

    python3 ~/screen-locker/scripts/verify_lock_popup_safety.py
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock import LockConfig, RecoveryLoop

from screen_locker import _manual_workout
from screen_locker._manual_workout_dialog import ManualWorkoutDialogMixin
from screen_locker._surface_group import FrameGroup
from screen_locker._ui_widgets import UIWidgetsMixin

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

TICK_MS = 1000
TICKS = 5
INNER_ENV = "_LOCK_POPUP_CHECK_INNER"


def reexec_under_xvfb() -> int:
    """Re-run this script on a throwaway X display, returning its exit code."""
    xvfb_run = shutil.which("xvfb-run")
    if xvfb_run is None:
        _logger.error(
            "xvfb-run not found. Install it with: sudo pacman -S --needed "
            "xorg-server-xvfb"
        )
        return 1
    env = dict(os.environ, **{INNER_ENV: "1"})
    # Absolute argv, no shell.
    return subprocess.run(
        [
            xvfb_run,
            "-a",
            "-s",
            "-screen 0 1600x1200x24",
            sys.executable,
            str(Path(__file__).resolve()),
        ],
        check=False,
        env=env,
    ).returncode


class HostileLock:
    """gatelock's two recovery-tick behaviours over a real Tk root."""

    def __init__(self, root: tk.Tk) -> None:
        """Take the global grab and start ticking."""
        self.root = root
        self.ticks = 0
        # A RecoveryLoop built only to borrow gatelock's real grab predicate;
        # this harness drives the ticks itself, so the collaborators are never
        # called -- the same MagicMock stand-ins gatelock's own tests use.
        self._loop = RecoveryLoop(
            root, LockConfig(mode="hard"), MagicMock(), MagicMock(), MagicMock()
        )
        root.grab_set_global()
        root.after(TICK_MS, self._tick)

    def _tick(self) -> None:
        """Lift the surface and re-take the grab, exactly as gatelock does."""
        self.ticks += 1
        self.root.lift()
        if not self._loop.holds_grab():
            self.root.grab_set_global()
        self.root.after(TICK_MS, self._tick)


def run_ticks(
    root: tk.Tk, judge: Callable[[], bool], setup: Callable[[], None] | None = None
) -> bool:
    """Tick hostilely TICKS times, then let ``judge`` say what survived.

    ``setup`` runs AFTER the lock has taken its grab, which is the order the
    real thing has: the user opens a widget on an already-grabbed lock. Posting
    a menu first would just let the lock's initial ``grab_set_global()`` take
    it, proving nothing about the recovery tick.
    """
    verdict = False

    def decide() -> None:
        nonlocal verdict
        verdict = judge()

    HostileLock(root)
    if setup is not None:
        root.after(200, setup)
    root.after(TICK_MS * TICKS + 400, decide)
    root.after(TICK_MS * TICKS + 600, root.quit)
    root.mainloop()
    root.destroy()
    return verdict


def leaf(name: object) -> str:
    """A Tk window path shortened to its last component, "root" for ``.``."""
    if not name:
        return "<nothing>"
    return str(name).rsplit(".", 1)[-1] or "root"


def grab_holder(root: tk.Tk) -> str:
    """The leaf name of whatever currently holds the grab."""
    return leaf(root.tk.call("grab", "current", root))


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


class FormHost(UIWidgetsMixin, ManualWorkoutDialogMixin):
    """The two hooks the mixin requires, over a real Tk root."""

    def __init__(self, root: tk.Tk) -> None:
        """Set only the attributes the form actually reads."""
        self.root = root
        self.demo_mode = False
        self.log_file = (
            Path(__file__).resolve().parent.parent
            / "screen_locker"
            / "workout_log.json"
        )
        self._colors = LockConfig()
        self.container = FrameGroup.single(root, bg=self._colors.bg)

    def _on_manual_workout_saved(self, entry: dict[str, object]) -> None:
        """Unused here; the form is never submitted."""

    def _on_manual_workout_cancelled(self) -> None:
        """Unused here; BACK is never pressed."""

    # Public wrappers so this script never reaches into the mixin's
    # private surface from outside the class.
    def render(self) -> None:
        """Paint the manual-workout form into the container."""
        self._show_manual_workout_form()

    def state(self) -> tuple[str, bool, bool]:
        """(selected sport code, other fields shown, table-tennis shown)."""
        return (
            self._current_mw_sport(),
            bool(self._mw_other_frame.winfo_ismapped()),
            bool(self._mw_tt_frame.winfo_ismapped()),
        )


def radios(widget: tk.Misc) -> list[tk.Radiobutton]:
    """Every Radiobutton under ``widget``, depth-first."""
    found: list[tk.Radiobutton] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Radiobutton):
            found.append(child)
        found.extend(radios(child))
    return found


def check_real_form_survives() -> bool:
    """Build the production form, pick "Other", hold it through the ticks."""
    root = tk.Tk()
    root.geometry("1600x1200+0+0")
    host = FormHost(root)
    host.render()
    root.update()

    buttons = radios(root)
    labels = [b.cget("text") for b in buttons]
    _logger.info("  sport radio buttons rendered: %s", labels)
    if len(buttons) != len(_manual_workout.SPORT_LABELS):
        _logger.error(
            "  expected one radio button per sport (%d), got %d",
            len(_manual_workout.SPORT_LABELS),
            len(labels),
        )
        root.destroy()
        return False

    def pick_other() -> None:
        buttons[1].invoke()
        root.update()

    def judge() -> bool:
        """The Other sport must still be selected, with its own fields shown."""
        sport, other_shown, tt_shown = host.state()
        _logger.info(
            "  radio buttons after %d ticks: grab=%s sport=%r other_fields=%s "
            "tt_fields=%s",
            TICKS,
            grab_holder(root),
            sport,
            other_shown,
            tt_shown,
        )
        return sport == _manual_workout.SPORT_OTHER and other_shown and not tt_shown

    return run_ticks(root, judge, setup=pick_other)


def main() -> int:
    """Run both checks under Xvfb and report which held."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if os.environ.get(INNER_ENV) != "1":
        return reexec_under_xvfb()

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
