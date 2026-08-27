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

from screen_locker._decision_log import record_no_decision
from screen_locker._manual_cli import run_manual_log
from screen_locker._status import run_status

if TYPE_CHECKING:
    from screen_locker.screen_lock import ScreenLocker

__all__ = ["main"]

_LOG_FILE_NAME = "log.json"
_LOG_MANUAL_FLAG = "--log-manual-workout"


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
    # Configure logging for EVERY mode, not just --sync-only. This used to sit
    # inside the --sync-only branch, so `--production` -- the mode systemd
    # actually runs -- had no handler and fell back to lastResort, which drops
    # everything below WARNING. The result: zero INFO lines from
    # workout-locker.service since June, and a thirteen-day enforcement outage
    # that left no trace at all. Never narrow this back to one branch.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if "--status" in argv:
        run_status(_headless_locker(locker_cls))

    if _LOG_MANUAL_FLAG in argv:
        # Headless manual logging: no Tk, no phone, no app in the foreground.
        # Everything after the flag is the workout's evidence, validated by
        # the same rules the phone form applies.
        rest = argv[argv.index(_LOG_MANUAL_FLAG) + 1 :]
        sys.exit(run_manual_log(_headless_locker(locker_cls).log_file, rest))

    if "--sync-only" in argv:
        # Headless sync for the timer unit: pull other devices' workouts and
        # apply their credit, with no Tk and no lock screen. Sync used to run
        # ONLY at process start, so a workout finished after login was not seen
        # until the next login — the timer closes that window.
        _headless_locker(locker_cls).sync_now()
        # Say so explicitly: --sync-only NEVER locks, so a reader tracing "why
        # didn't it lock?" through the journal must not mistake a sync run for
        # an enforcement run that decided to skip.
        record_no_decision("--sync-only")
        sys.exit(0)

    locker = locker_cls(
        demo_mode="--production" not in argv,
        verify_only="--verify-workout" in argv,
    )
    locker.run()
