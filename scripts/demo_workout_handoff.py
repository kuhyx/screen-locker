"""Try the workout-app handoff by hand, with one deliberate way out.

The lock itself is the real one: the demo builds the same lock window and the
workout app takes the same exclusive seat grab it takes in production, so what
is under test is the actual locking mechanism, not a softened copy.

Getting the escape right took two wrong tries, both worth recording because
they are the obvious ideas:

1. A Tk key binding cannot work. Once the workout app takes its seat grab
   (``gdk_seat_grab`` with ``GDK_SEAT_CAPABILITY_ALL``) X delivers every
   keystroke to that app and to nothing else, so no binding in this process
   can fire -- no matter how healthy its event loop is.
2. "Escape from another terminal" cannot work either. The app covers the
   screen with an override-redirect fullscreen window, so there is no other
   terminal to reach and no way to raise one.

An escape therefore has to be handled INSIDE the app, by the app, or it cannot
be reached at all. ``--demo-escape`` (passed here, never by the production
supervisor) arms a key handler in the runner that drops the grab and quits:

    Ctrl+Shift+Q

Verified in both directions: with the flag the real app exits on that
keystroke while holding the grab; without it the same keystroke does nothing.

VT switching is left enabled here as a second line of defence, so Ctrl+Alt+F2
also still works -- but the hatch above is the one this demo is testing.

One thing a green run does NOT prove: under the demo's local grab gatelock's
watchdog early-returns and never re-takes the grab, so the 1000ms steal-back
that makes ``_recovery.stop()`` load-bearing in production is not exercised.

    python3 scripts/demo_workout_handoff.py
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gatelock import LockConfig, LockWindow

from screen_locker._workout_app import ProcessHooks, workout_app_binary
from screen_locker._workout_handoff import lock_grab_handoff
from screen_locker._workout_session import WorkoutSession


class _DemoHooks:
    """A minimal lock body: a status line and the two buttons under test."""

    def __init__(self) -> None:
        self.status: tk.Label | None = None
        self.lock: LockWindow | None = None
        self.session: WorkoutSession | None = None

    def build_surface(self, parent: tk.Misc, _surface: object) -> None:
        tk.Label(
            parent,
            text="DEMO LOCK — local grab, VT switching still enabled",
            font=("TkDefaultFont", 18, "bold"),
            bg="#1B1D21",
            fg="#E6E6E6",
        ).pack(pady=(120, 8))
        self.status = tk.Label(
            parent,
            text=(
                "Press “Start workout”. While the app holds the screen, "
                "press Ctrl+Shift+Q to escape."
            ),
            font=("TkDefaultFont", 12),
            bg="#1B1D21",
            fg="#9AA0A6",
        )
        self.status.pack(pady=8)
        tk.Button(
            parent,
            text="Start workout",
            font=("TkDefaultFont", 14, "bold"),
            bg="#3B82F6",
            fg="#FFFFFF",
            padx=24,
            pady=12,
            command=self._start,
        ).pack(pady=16)
        tk.Button(
            parent,
            text="✕ Close demo (or press Escape)",
            bg="#EF4444",
            fg="#FFFFFF",
            command=self._close,
        ).pack(pady=4)

    def _start(self) -> None:
        if self.lock is None or self.status is None:  # pragma: no cover
            return
        self.session = WorkoutSession(
            lock_grab_handoff(self.lock),
            after=self.lock.root.after,
            on_status=self._set_status,
            # The only escape that can be RECEIVED once the app grabs the seat.
            hooks=ProcessHooks(demo_escape=True),
        )
        self.session.start()

    def _set_status(self, text: str) -> None:
        if self.status is not None:  # pragma: no branch
            self.status.config(text=text)

    def _close(self) -> None:
        if self.lock is not None:  # pragma: no cover
            self.lock.close()

    def teardown_surface(self, _surface: object) -> None: ...

    def on_focus_ready(self, _surface: object) -> None: ...

    def on_close(self) -> None: ...


def main() -> int:
    """Run the demo lock. Returns non-zero when the app is not built."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if workout_app_binary() is None:
        return 1
    root = tk.Tk()
    root.title("Workout handoff demo")
    # Local grab + VT switching enabled: every escape hatch stays open.
    config = LockConfig(mode="hard", grab="local", disable_vt=False)
    hooks = _DemoHooks()
    lock = LockWindow(root, config, hooks)
    hooks.lock = lock
    lock.setup()
    root.bind("<Escape>", lambda _event: lock.close())
    lock.grab_input()
    lock.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
