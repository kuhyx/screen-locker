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

from screen_locker._constants import SHUTDOWN_BASE_FILE
from screen_locker._decision_log import record_no_decision
from screen_locker._manual_cli import run_manual_log
from screen_locker._rest_day_cli import run_declare_rest_day
from screen_locker._shutdown_base import apply_flat_bonuses_if_new
from screen_locker._status import run_status
from screen_locker._workout_ledger_cli import run_backfill

if TYPE_CHECKING:
    from screen_locker.screen_lock import ScreenLocker

__all__ = ["main"]

_logger = logging.getLogger(__name__)

_LOG_FILE_NAME = "log.json"
_LOG_MANUAL_FLAG = "--log-manual-workout"
_REST_DAY_FLAG = "--declare-rest-day"
_BACKFILL_FLAG = "--backfill-workout-ledger"

# Subcommands that own every argument after them (each has its own argparse,
# which also answers its own --help).
_TRAILING_ARG_FLAGS = (_LOG_MANUAL_FLAG, _REST_DAY_FLAG, _BACKFILL_FLAG)
_MODE_FLAGS = frozenset(
    {"--status", "--sync-only", "--apply-bonuses", "--production", "--verify-workout"}
)
_HELP_FLAGS = frozenset({"-h", "--help"})
_EXIT_USAGE = 2

_USAGE = """\
usage: python3 -m screen_locker.screen_lock [MODE]

With no mode: the demo lock screen (Tk). Modes:
  --production                 the real lock screen (what workout-locker.service runs)
  --verify-workout             lock screen in verify-only mode
  --status                     print this week's workout status and exit
  --sync-only                  headless: pull synced workouts, apply credit, exit
  --apply-bonuses              headless: apply newly earned flat bonuses, exit
  --log-manual-workout ARGS    headless manual workout log (see its --help)
  --declare-rest-day ARGS      sign a future rest day (see its --help)
  --backfill-workout-ledger ARGS
                               backfill the workout ledger (see its --help)
  -h, --help                   show this help and exit
"""


def _own_args(argv: list[str]) -> list[str]:
    """``argv[1:]`` up to the first subcommand that owns the rest."""
    args = argv[1:]
    for index, arg in enumerate(args):
        if arg in _TRAILING_ARG_FLAGS:
            return args[:index]
    return args


def _handle_help_and_unknown(argv: list[str]) -> None:
    """Exit 0 on ``--help``; exit 2 on an unknown argument.

    Before this, ``--help`` matched no branch and fell through to building
    the demo lock screen, and a typo'd flag did the same silently.
    """
    own = _own_args(argv)
    if _HELP_FLAGS & set(own):
        # The usage on stdout IS the work --help asked for, so exiting 0 here
        # abandons nothing. SystemExit is raised directly, not via sys.exit:
        # the suite stubs sys.exit process-wide, and a help request must never
        # fall through to building the lock screen even then.
        sys.stdout.write(_USAGE)
        raise SystemExit(0)
    unknown = [arg for arg in own if arg not in _MODE_FLAGS]
    if unknown:
        sys.stderr.write(f"error: unknown argument(s): {' '.join(unknown)}\n{_USAGE}")
        sys.exit(_EXIT_USAGE)


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
    _handle_help_and_unknown(argv)
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

    if _REST_DAY_FLAG in argv:
        # Headless, no Tk: sign a FUTURE rest day (see screen_locker._rest_day).
        sys.exit(run_declare_rest_day(argv[argv.index(_REST_DAY_FLAG) + 1 :]))

    if _BACKFILL_FLAG in argv:
        rest = argv[argv.index(_BACKFILL_FLAG) + 1 :]
        sys.exit(run_backfill(_headless_locker(locker_cls).log_file, rest))

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

    if "--apply-bonuses" in argv:
        # earner-bonus.service, started by earner-bonus.path when a gate
        # writes its ledger: only the flat-bonus pass, no phone sync, so a
        # solve moves shutdown within seconds rather than at the next sync.
        _logger.info("Ledger changed: applying any newly earned flat bonus.")
        apply_flat_bonuses_if_new(SHUTDOWN_BASE_FILE, _headless_locker(locker_cls))
        record_no_decision("--apply-bonuses")
        sys.exit(0)

    locker = locker_cls(
        demo_mode="--production" not in argv,
        verify_only="--verify-workout" in argv,
    )
    locker.run()
