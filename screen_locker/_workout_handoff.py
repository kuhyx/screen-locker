"""Handing the lock screen to the workout app, and taking it back.

The Tk locker cannot simply ``close()`` to let the app take over: ``close()``
also restores VT switching, which would hand the user Ctrl+Alt+F2 and an exit
from the very obligation the lock exists to enforce. Only the *grab* moves.

The recovery watchdog has to be stopped for the duration, and that is the part
that is easy to get wrong. It is built never to release -- it re-takes a grab
it finds missing, deliberately, so that pulling a cable is not an escape. Left
running it would treat the Flutter app exactly like an intruder and steal the
screen back within one verify tick, mid-workout. So the order is: stop the
watchdog, release the grab, run the app, re-take the grab, restart the
watchdog. The Tk window itself stays mapped underneath the whole time, which
is what keeps the screen covered if the app dies.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from typing import TYPE_CHECKING

from screen_locker._workout_app import GrabHandoff, launch_workout_app

if TYPE_CHECKING:
    from gatelock import LockWindow

__all__ = ["lock_grab_handoff", "start_workout"]

_logger = logging.getLogger(__name__)


def lock_grab_handoff(lock: LockWindow) -> GrabHandoff:
    """Build the release/reacquire pair for a live lock window.

    Neither direction touches VT switching or the arbiter claim: this is a
    loan of the grab, not a teardown.
    """

    def release() -> None:
        # Stop first: a watchdog tick between the release and the app's own
        # grab would take the screen straight back off it.
        lock._recovery.stop()
        with contextlib.suppress(tk.TclError):
            lock.root.grab_release()
        _logger.warning(
            "Released the X grab to the workout app; the lock window stays "
            "mapped and VT switching stays disabled."
        )

    def reacquire() -> None:
        # Unconditional and idempotent: whatever happened to the app, this
        # machine must not be left with nothing holding the screen.
        lock.grab_input()
        _logger.warning("Re-took the X grab from the workout app.")

    return GrabHandoff(release=release, reacquire=reacquire)


def start_workout(lock: LockWindow) -> str:
    """Run the workout app as the lock surface; return a status for the UI.

    Never raises: this is wired to a button on a screen the user cannot leave,
    so a failure has to come back as a message rather than a traceback that
    would leave the grab in an unknown state.

    Blocks until the app exits, which stops the Tk event loop for the whole
    workout. That is deliberate rather than merely tolerated: the Flutter
    window is covering the screen, and the alternative -- pumping Tk
    underneath -- is what would let the watchdog tick and take the screen back
    mid-set. The cost is that a monitor hotplug during the workout is not
    handled until the app exits, when ``reacquire`` re-runs ``grab_input()``
    and the watchdog re-covers every live output.
    """
    result = launch_workout_app(lock_grab_handoff(lock))
    if not result.launched:
        _logger.error("Could not start the PC workout: %s", result.reason)
        return f"Could not start the workout: {result.reason}"
    _logger.warning("The workout app finished: %s", result.reason)
    return "Workout app closed — checking whether it counted…"
