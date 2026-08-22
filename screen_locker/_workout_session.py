"""Running the workout app without freezing the lock's event loop.

``launch_workout_app`` blocks until the app exits, which is fine for a
headless caller but wrong behind a Tk button: while it blocks, the event loop
is not running, so key bindings and buttons on the lock itself are inert. In
the demo lock -- whose whole promise is that Escape always works -- that
turned a "safe" screen into one that needed a hard reboot to leave.

So the phases are driven by ``after`` instead, on the main thread. Every Tk
call (``grab_release``, ``grab_input``) stays there, which a worker thread
could not guarantee, and the loop keeps pumping the entire time the app is up.

This does not weaken the production handoff. The grab is still released only
after the ready line, and the recovery watchdog is still stopped first -- and
because ``stop()`` cancels its timers outright, there are no ticks to race
with while the app runs.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from screen_locker._workout_app import ProcessHooks, workout_app_binary
from screen_locker._workout_ready import READY_MARKER

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from typing import IO, Protocol

    from screen_locker._workout_app import GrabHandoff

    class _Child(Protocol):
        """The half of ``subprocess.Popen`` this module drives."""

        stdout: IO[str] | None
        returncode: int | None

        def poll(self) -> int | None: ...

        def terminate(self) -> None: ...


__all__ = ["WorkoutSession"]

_logger = logging.getLogger(__name__)

# How often to look at the app while it runs. Short enough that the lock comes
# back promptly when the app exits, long enough not to spin the event loop.
_POLL_MS = 100

# 600 polls x 100ms = 60s, matching the blocking supervisor's own deadline.
_READY_TIMEOUT_POLLS = 600


class WorkoutSession:
    """One supervised run of the workout app, driven by the Tk event loop.

    ``on_status`` is called with a human-readable line at each transition, so a
    failure is visible on the lock screen rather than only in the journal.
    """

    def __init__(
        self,
        handoff: GrabHandoff,
        *,
        after: Callable[[int, Callable[[], None]], object],
        on_status: Callable[[str], None],
        binary: Path | None = None,
        hooks: ProcessHooks | None = None,
    ) -> None:
        self._handoff = handoff
        self._after = after
        self._on_status = on_status
        self._binary = binary
        self._hooks = hooks if hooks is not None else ProcessHooks()
        self._remaining = _READY_TIMEOUT_POLLS
        self._child: _Child | None = None
        self._seen = ""
        self._released = False

    def start(self) -> None:
        """Spawn the app; the rest happens on later event-loop turns."""
        app = self._binary if self._binary is not None else workout_app_binary()
        if app is None:
            self._fail("the desktop workout app is not built; run flutter build linux")
            return
        self._child = self._hooks.popen(
            [str(app), "--lock-mode"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._on_status("Starting the workout app…")
        self._after(_POLL_MS, self._await_ready)

    def _await_ready(self) -> None:
        """Watch for the ready line without ever blocking the loop."""
        child = self._child
        stdout = getattr(child, "stdout", None)
        if stdout is None:
            self._fail("the workout app exited before signalling ready")
            return
        # Zero timeout: ask what is there right now and return to the loop.
        readable, _, _ = self._hooks.selector([stdout], [], [], 0)
        if readable:
            chunk = _read_available(stdout)
            if not chunk:
                self._fail("the workout app exited before signalling ready")
                return
            self._seen += chunk
            if READY_MARKER in self._seen:
                self._release_and_watch()
                return
        self._remaining -= 1
        if self._remaining <= 0:
            # Never release to a window that may not be up.
            child.terminate()
            self._fail("the workout app never signalled ready in time")
            return
        self._after(_POLL_MS, self._await_ready)

    def _release_and_watch(self) -> None:
        self._handoff.release()
        self._released = True
        self._on_status("The workout app has the screen.")
        self._after(_POLL_MS, self._watch_until_exit)

    def _watch_until_exit(self) -> None:
        if self._child.poll() is None:
            self._after(_POLL_MS, self._watch_until_exit)
            return
        self.finish()

    def finish(self) -> None:
        """Take the screen back. Idempotent, so an early abort is safe."""
        if self._released:
            self._released = False
            self._handoff.reacquire()
        code = getattr(self._child, "returncode", None)
        _logger.warning("The workout app exited with code %s.", code)
        self._on_status("Workout app closed — checking whether it counted…")

    def abort(self) -> None:
        """Kill the app and restore the lock, whatever phase we are in."""
        child = self._child
        if child is not None and child.poll() is None:
            child.terminate()
            _logger.warning("Workout app terminated by an explicit abort.")
        self.finish()

    def _fail(self, reason: str) -> None:
        _logger.error("Could not run the PC workout: %s", reason)
        self._on_status(f"Could not start the workout: {reason}")


def _read_available(stream: IO[str]) -> str:
    """Read what the pipe holds now; see ``_workout_ready`` for the why."""
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return stream.readline()
    return buffer.read1().decode("utf-8", "replace")
