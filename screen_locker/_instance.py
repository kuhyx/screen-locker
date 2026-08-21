"""One workout-locker process at a time.

A stray re-arm (a delayed ``workout-locker.timer`` catch-up landing right on
top of a session that just unlocked, a direct spawn outside the tracked
systemd unit, or any other double-start) used to mean two Tk processes
racing to build a lock window and grab the display. Copied in shape from
``leetcode_guard._instance`` / ``diet_guard._gatelock.acquire_gate_lock``.

Liveness is the kernel's ``flock``, held for the process lifetime: it is
released on *any* death, including SIGKILL and a crashed X server. No PID
files, no staleness heuristics, no timeouts.
"""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import logging
import os
from typing import IO, TYPE_CHECKING, Final

_logger: Final = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class InstanceLock:
    """A held single-instance lock."""

    handle: IO[str]
    path: Path

    def release(self) -> None:
        """Drop the lock. Idempotent, and safe on a closed handle."""
        try:
            self.handle.close()
        except OSError as exc:
            _logger.warning("could not close the instance lock %s: %s", self.path, exc)


def acquire(path: Path) -> InstanceLock | None:
    """Take the single-instance lock, or ``None`` if another run holds it.

    Opened ``"a+"`` rather than ``"w"``: ``"w"`` truncates at ``open()`` time,
    which happens *before* the lock attempt, so a losing contender would erase
    the incumbent's record on its way out.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
    except OSError:
        _logger.exception("cannot open the instance lock %s", path)
        return None
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _logger.warning(
            "another workout-locker run already holds %s -- standing down", path
        )
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return InstanceLock(handle=handle, path=path)
