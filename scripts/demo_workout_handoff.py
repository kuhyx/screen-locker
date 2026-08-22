"""Try the workout-app handoff by hand, on a lock you can always escape.

Deliberately NOT the production lock screen. This builds a demo-mode lock --
``grab="local"``, VT switching left enabled -- so a wedged Flutter app can
never trap you: Ctrl+Alt+F2, the window manager, and the Escape binding below
all still work. Production uses a global grab and disables VT switching, which
is exactly what makes it unsafe to poke at by hand.

One consequence worth knowing before you read anything into a green run: under
a local grab gatelock's watchdog early-returns and never re-takes the grab, so
this exercises the launch, the ready handshake and the reacquire, but NOT the
1000ms steal-back that the global grab makes possible.

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
from screen_locker._workout_handoff import start_workout


class _DemoHooks:
    """A minimal lock body: a status line and the two buttons under test."""

    def __init__(self) -> None:
        self.status: tk.Label | None = None
        self.lock: LockWindow | None = None

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
            text="Press “Start workout” to hand this screen to the app.",
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
        self.status.config(text="Launching… the screen is handed over shortly.")
        self.status.update_idletasks()
        # Blocks for the whole workout, by design -- see start_workout's
        # docstring. The demo window stops repainting until the app exits.
        self.status.config(text=start_workout(self.lock))

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
