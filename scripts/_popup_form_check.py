"""The real manual-workout form, checked for popups, plus the tick helpers.

Split out of ``verify_lock_popup_safety.py`` to keep every file under the
250-line cap. That script imports ``check_real_form_survives`` and runs it as
one of its two checks.

The point of the check: the evidence form must build every widget inline on
the lock surface. A widget that opens its own toplevel (an OptionMenu, a
messagebox) would appear *above* the lock and hand back an escape hatch.
"""

from __future__ import annotations

import logging
from pathlib import Path
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
        self.root.lift()
        if not self._loop.holds_grab():
            self.root.grab_set_global()
        # Counted only after the work, so a raising tick does not count. Tk
        # swallows exceptions from `after` callbacks, and this harness once
        # reported OK while every tick was dying on an AttributeError.
        self.ticks += 1
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

    lock = HostileLock(root)
    if setup is not None:
        root.after(200, setup)
    root.after(TICK_MS * TICKS + 400, decide)
    root.after(TICK_MS * TICKS + 600, root.quit)
    root.mainloop()
    root.destroy()
    if lock.ticks < TICKS:
        _logger.error(
            "  only %d of %d hostile ticks completed -- the harness itself is "
            "broken, so this result proves nothing",
            lock.ticks,
            TICKS,
        )
        return False
    return verdict


def leaf(name: object) -> str:
    """A Tk window path shortened to its last component, "root" for ``.``."""
    if not name:
        return "<nothing>"
    return str(name).rsplit(".", 1)[-1] or "root"


def grab_holder(root: tk.Tk) -> str:
    """The leaf name of whatever currently holds the grab."""
    return leaf(root.tk.call("grab", "current", root))


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
