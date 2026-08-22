"""Launching the desktop workout app as the lock surface.

The phone is gone, so the workout has to be doable on the PC — but handing the
user a normal desktop window while the lock screen is up would mean unlocking
the machine to earn the unlock. Instead the Flutter app becomes the lock: it
takes the same override-redirect fullscreen window and the same exclusive X
grab the Tk locker holds, with no way out but finishing or resetting.

Two X clients cannot hold the grab at once (verified: the second gets
``grab failed: another application has grab``), so the two windows hand it
over in a fixed order:

1. Tk keeps the grab and launches the app.
2. The app maps fullscreen ON TOP and starts retrying the grab, failing while
   Tk still holds it, and prints ``WORKOUT_LOCK: ready``.
3. Only then does Tk release — so the screen is covered continuously rather
   than exposing the desktop for the whole of Flutter's cold start.

Releasing the *grab* is deliberate: ``gatelock``'s ``close()`` also restores
VT switching, so tearing the Tk window down here would re-enable
Ctrl+Alt+F2 and hand the user an exit. The Tk process stays alive as the
supervisor and re-takes the grab if the app dies.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING

from screen_locker._workout_ready import (
    READY_MARKER,
    await_ready,
    default_selector,
)

if TYPE_CHECKING:
    from screen_locker._workout_ready import _Selector

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import IO, Protocol

    class _Child(Protocol):
        """The half of ``subprocess.Popen`` this module actually drives."""

        stdout: IO[str] | None
        returncode: int | None

        def terminate(self) -> None: ...

        def wait(self) -> int: ...

    class _Spawner(Protocol):
        """``subprocess.Popen``, narrowed to the one call shape used here."""

        def __call__(
            self,
            args: Sequence[str],
            *,
            stdout: int,
            stderr: int,
            text: bool,
            bufsize: int,
        ) -> _Child: ...


__all__ = [
    "READY_MARKER",
    "GrabHandoff",
    "ProcessHooks",
    "WorkoutAppResult",
    "launch_workout_app",
    "workout_app_binary",
]

_logger = logging.getLogger(__name__)

# Where `flutter build linux` puts the bundle, relative to the repo root.
_BUNDLE = Path("stronglift_replacement/workout_app/build/linux/x64")
_BINARY_NAME = "workout_app"

# A cold Flutter start opens the DB and pulls progression (bounded at 20s in
# the app's own main()), so the ready line can legitimately take a while.
READY_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class GrabHandoff:
    """The two halves of passing the screen to the app and taking it back.

    Injected so the handoff is testable without an X server, and so it is
    obvious at the call site that *both* directions must be provided.
    """

    release: Callable[[], None]
    reacquire: Callable[[], None]


@dataclass(frozen=True)
class ProcessHooks:
    """How the supervisor spawns the app and waits on its output.

    One seam because they are always substituted together: a test that fakes
    the process must fake the wait too.
    """

    popen: _Spawner = subprocess.Popen
    selector: _Selector = default_selector


class WorkoutAppResult:
    """Outcome of one supervised workout-app run.

    Carries a human-readable ``reason`` so a failed launch says what happened
    instead of silently dropping the user back to the lock screen.
    """

    def __init__(self, *, launched: bool, reason: str) -> None:
        self.launched = launched
        self.reason = reason

    def __repr__(self) -> str:
        return f"WorkoutAppResult(launched={self.launched}, reason={self.reason!r})"


def workout_app_binary(repo_root: Path | None = None) -> Path | None:
    """Return the built desktop app, or None when it has not been built.

    Prefers the release bundle and falls back to debug, so a machine that has
    only ever run ``flutter build linux --debug`` still works.
    """
    root = (
        repo_root if repo_root is not None else Path(__file__).resolve().parent.parent
    )
    for flavour in ("release", "debug"):
        candidate = root / _BUNDLE / flavour / "bundle" / _BINARY_NAME
        if candidate.exists():
            return candidate
    _logger.error(
        "The desktop workout app is not built at %s (release or debug) — the "
        "lock screen cannot offer a PC workout. Build it with: "
        "cd stronglift_replacement/workout_app && flutter build linux --release",
        root / _BUNDLE,
    )
    return None


def launch_workout_app(
    handoff: GrabHandoff,
    *,
    binary: Path | None = None,
    resolve_binary: Callable[[], Path | None] = workout_app_binary,
    hooks: ProcessHooks | None = None,
    ready_timeout: float = READY_TIMEOUT_SECONDS,
) -> WorkoutAppResult:
    """Run the workout app as the lock surface, then restore the Tk grab.

    Blocks until the app exits; the caller re-evaluates compliance afterwards
    (a finished workout reaches ``log.json`` through the normal sync path, not
    through this function's return value).
    """
    io = hooks if hooks is not None else ProcessHooks()
    app = binary if binary is not None else resolve_binary()
    if app is None:
        return WorkoutAppResult(
            launched=False,
            reason="the desktop workout app is not built; run flutter build linux",
        )

    child = io.popen(
        [str(app), "--lock-mode"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    ready, why = await_ready(child, ready_timeout, io.selector)
    if not ready:
        # Never release the grab to a window that may not be up: that is the
        # one failure mode that leaves the machine unlocked.
        child.terminate()
        return WorkoutAppResult(
            launched=False,
            reason=(
                f"{why} — keeping the lock screen up rather than releasing the "
                "screen to a window that may not have started"
            ),
        )

    handoff.release()
    try:
        child.wait()
    finally:
        # Unconditional: however the app exited, this machine must not be
        # left with nothing holding the screen.
        handoff.reacquire()
    return WorkoutAppResult(
        launched=True,
        reason=f"the workout app exited with code {child.returncode}",
    )
