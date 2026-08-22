"""Waiting for the workout app's ready line on a pipe that may stall.

Split from ``_workout_app`` for the 250-line cap: this is the whole of the
"is the app up yet?" protocol, and it is the part with the sharp edges.

``readline()`` on a pipe blocks until a newline arrives, so polling the clock
around it cannot enforce a timeout -- an app that starts and prints nothing,
or leaves half a line in the buffer, would hold the lock screen forever and
then be misreported as having exited. Everything here exists to make the
deadline real.
"""

from __future__ import annotations

import logging
import select
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import IO, Protocol

    _Streams = Sequence[IO[str]]

    class _Selector(Protocol):
        """``select.select``, narrowed to the readable-wait used here."""

        def __call__(
            self, rlist: _Streams, wlist: _Streams, xlist: _Streams, timeout: float
        ) -> tuple[list[IO[str]], list[IO[str]], list[IO[str]]]: ...

    class _HasStdout(Protocol):
        """The half of the child process this module reads from."""

        stdout: IO[str] | None


__all__ = ["READY_MARKER", "await_ready", "default_selector"]

_logger = logging.getLogger(__name__)

# Printed by linux/runner/my_application.cc once the window is mapped and the
# grab retry loop is running. The supervisor waits for this before releasing.
READY_MARKER = "WORKOUT_LOCK: ready"

default_selector = select.select


def _read_available(stream: IO[str]) -> str:
    """Read whatever the pipe currently holds, without waiting for a newline.

    ``select`` has already said the stream is readable. Text streams wrap a
    binary buffer whose ``read1`` returns the available bytes immediately;
    ``readline`` would instead block until a newline, which is what let a
    half-written line outlive the deadline. Fakes with no ``buffer`` fall back
    to a line, which never blocks for them.
    """
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return stream.readline()
    return buffer.read1().decode("utf-8", "replace")


def await_ready(
    child: _HasStdout, timeout: float, selector: _Selector = default_selector
) -> tuple[bool, str]:
    """Wait for the app's ready line, or for it to die first.

    Returns ``(ready, why)``; ``why`` distinguishes a crash from a hang, which
    need different fixes (a broken build vs. a slow first sync).

    The wait is ``select``-based, and reads whatever is available rather than
    whole lines, because ``readline()`` on a real pipe blocks until a newline
    arrives. Polling the clock around a blocking read cannot enforce a
    timeout, so an app that started and printed nothing -- or left a half
    written line in the pipe -- would hold the lock screen forever and then be
    misreported as having exited.
    """
    deadline = time.monotonic() + timeout
    seen = ""
    while (remaining := deadline - time.monotonic()) > 0:
        if child.stdout is None:
            return _not_ready("the workout app exited before signalling ready")
        readable, _, _ = selector([child.stdout], [], [], remaining)
        if not readable:
            break
        chunk = _read_available(child.stdout)
        if not chunk:
            # Nothing left to read AND the pipe is at EOF: the app is gone.
            return _not_ready("the workout app exited before signalling ready")
        # Accumulated, not matched per read: a chunk boundary can fall inside
        # the marker, and dropping it would strand a healthy app at the lock.
        seen += chunk
        if READY_MARKER in seen:
            return True, "ready"
    reason = f"the workout app never signalled ready within {timeout:.0f}s"
    _logger.error("%s (expected %r on stdout).", reason, READY_MARKER)
    return False, reason


def _not_ready(reason: str) -> tuple[bool, str]:
    """Log a failed start loudly, so a dead app never fails silently."""
    _logger.error(
        "%s — the lock screen stays up and the workout was NOT started.", reason
    )
    return False, reason
