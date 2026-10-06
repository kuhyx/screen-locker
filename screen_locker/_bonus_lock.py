"""One writer at a time for the shutdown bonus state.

The daily reset and the live bonus pass both read ``shutdown_base.json``,
push ``/etc/shutdown-schedule.conf`` with a read-add-write and stamp the file.
They run from three processes -- the locker at login, the 15-minute
``workout-sync`` pass and the ledger-triggered ``earner-bonus`` pass -- so two
of them can see the same unstamped earner and each add its time. Holding this
lock across check, write and stamp makes the second one see the stamp.

A dedicated file, not the state file itself: ``_save_state`` truncates that.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["bonus_lock"]


@contextmanager
def bonus_lock(state_file: Path) -> Iterator[None]:
    """Hold an exclusive lock beside *state_file* for the ``with`` body.

    Blocks until any other holder is done; the passes it serialises take a
    second or two, so waiting is cheaper than skipping a bonus.
    """
    with state_file.with_suffix(".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
