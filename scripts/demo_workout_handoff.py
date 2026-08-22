"""Try the workout-app handoff by hand, on a lock you can always escape.

Deliberately NOT the production lock screen: ``grab="local"`` and VT switching
left enabled, so nothing here can outlive a Ctrl+Alt+F2.

The escapes are the point, and the first version of this script got them
wrong in two independent ways -- it promised three and delivered none, and the
only way out was a hard reboot. Both are fixed here, and both are worth
knowing about because only one of them was a demo-only problem:

1. ``launch_workout_app`` blocks until the app exits. Called straight from a
   button, it froze the Tk event loop, so the Escape binding and the close
   button could not fire. The run is driven by :class:`WorkoutSession` now,
   which uses ``after`` and keeps the loop pumping.
2. The Flutter app takes its OWN seat grab (``gdk_seat_grab`` with
   ``GDK_SEAT_CAPABILITY_ALL``) and never releases it. That is correct for
   production and fatal for a demo: while the app is up, X delivers keyboard
   input to it, so no Tk binding of ours can fire no matter how healthy the
   event loop is. So the escape hatch below is deliberately NOT a key binding
   -- it is a file the app cannot intercept.

While the workout app is on screen, escape it from any other terminal or VT:

    touch ~/.cache/stop-workout-demo

A watchdog polls that path and terminates the app, which hands the screen
back. Ctrl+Alt+F2 also still works, because neither this script nor
``enter_lock_mode`` disables VT switching.

One thing a green run here does NOT prove: under a local grab gatelock's
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

from screen_locker._workout_app import workout_app_binary
from screen_locker._workout_handoff import lock_grab_handoff
from screen_locker._workout_session import WorkoutSession

# Polled while the app holds the seat grab; the one escape X cannot swallow.
# Under $HOME rather than /tmp: predictable for the user, and not world-writable.
ESCAPE_FILE = Path.home() / ".cache" / "stop-workout-demo"


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
                "Press “Start workout”. To escape while the app holds the "
                f"screen, run:  touch {ESCAPE_FILE}"
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
        ESCAPE_FILE.unlink(missing_ok=True)
        self.session = WorkoutSession(
            lock_grab_handoff(self.lock),
            after=self.lock.root.after,
            on_status=self._set_status,
        )
        self.session.start()
        self._poll_escape_file()

    def _set_status(self, text: str) -> None:
        if self.status is not None:  # pragma: no branch
            self.status.config(text=text)

    def _poll_escape_file(self) -> None:
        """The escape the Flutter app's seat grab cannot intercept."""
        if self.session is None or self.lock is None:  # pragma: no cover
            return
        if ESCAPE_FILE.exists():
            ESCAPE_FILE.unlink(missing_ok=True)
            self.session.abort()
            self.session = None
            return
        self.lock.root.after(200, self._poll_escape_file)

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
