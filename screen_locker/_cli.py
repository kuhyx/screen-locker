"""Command-line entry points for ``screen_lock.py``.

Split out of ``screen_lock.py`` to keep every file under the 250-line cap.
The argument handling lives here; ``screen_lock.py`` keeps only the
``ScreenLocker`` class and a one-line ``__main__`` delegation, so the module
that every mixin imports stays small.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from screen_locker._status import run_status

if TYPE_CHECKING:
    from screen_locker.screen_lock import ScreenLocker

__all__ = ["main"]

_LOG_FILE_NAME = "workout_log.json"


def _headless_locker(locker_cls: type[ScreenLocker]) -> ScreenLocker:
    """A ScreenLocker with ``__init__`` bypassed, for the no-UI subcommands.

    ``--status`` and ``--sync-only`` touch only ``log_file`` and
    ``workout_data``; constructing the real object would build a Tk UI and,
    in the ``--production`` case, grab the screen.
    """
    locker = object.__new__(locker_cls)
    locker.log_file = Path(__file__).resolve().parent / _LOG_FILE_NAME
    locker.workout_data = {}
    return locker


def main(locker_cls: type[ScreenLocker], argv: list[str]) -> None:
    """Dispatch on ``argv`` and run the requested mode."""
    if "--status" in argv:
        run_status(_headless_locker(locker_cls))

    if "--sync-only" in argv:
        # Headless sync for the timer unit: pull other devices' workouts and
        # apply their credit, with no Tk and no lock screen. Sync used to run
        # ONLY at process start, so a workout finished after login was not seen
        # until the next login — the timer closes that window.
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )
        _headless_locker(locker_cls).sync_now()
        sys.exit(0)

    locker = locker_cls(
        demo_mode="--production" not in argv,
        verify_only="--verify-workout" in argv,
    )
    locker.run()
