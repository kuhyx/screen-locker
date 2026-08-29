#!/usr/bin/env python3
"""Fail loudly when the screen locker is not actually armed.

The 2026-08 outage was not a logic bug. Every predicate worked; the timer that
*invokes* them had been disabled by a systemd ordering cycle, and nothing on the
machine considered that worth mentioning. ``systemctl status`` showed no failed
unit, because a job deleted to break a cycle is not a failure -- it is an
absence, and absences do not page anyone.

This script turns that absence into a loud, deterministic failure. It answers
one question -- *would enforcement actually happen?* -- and answers it from
systemd's own view rather than from the unit files on disk, because the files
were correct-looking the entire time the timer sat disabled.

Run it from the periodic sync timer (``workout-sync.service``), so the check
rides along with a unit already proven healthy instead of adding another timer
that could itself silently die.

Output goes through ``sys.stderr.write`` rather than ``print`` to match the
other gate scripts in this directory (see ``check_silent_failures.py``), which
keeps the repo free of T201 waivers.

Usage:
    python3 scripts/check_enforcement_armed.py          # exit 1 if disarmed
    python3 scripts/check_enforcement_armed.py --quiet  # only report problems
"""

from __future__ import annotations

import argparse
import logging
import sys

from screen_locker._armed_state import collect_states, systemctl_available

_logger = logging.getLogger(__name__)


def _report(message: str) -> None:
    """Write one line to stderr, so a disarmed locker is visible in the unit.

    Args:
        message: The line to write.
    """
    sys.stderr.write(f"{message}\n")


def main(argv: list[str] | None = None) -> int:
    """Report arming state; return 1 when enforcement would not happen."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only when something is wrong",
    )
    args = parser.parse_args(argv)

    if not systemctl_available():
        # Reachable in containers/CI. Say so explicitly rather than passing:
        # "could not check" must never be recorded as "checked and fine".
        _logger.error("systemctl not found — the arming check could not run")
        _report(
            "ERROR: systemctl not found — cannot verify that the screen locker "
            "is armed. This check did NOT pass; it did not run."
        )
        return 1

    states = collect_states()
    disarmed = [state for state in states if not state.armed]

    if disarmed:
        _logger.error(
            "Screen locker is NOT armed: %s",
            ", ".join(state.name for state in disarmed),
        )
        _report(
            "ERROR: the screen locker is NOT armed — a day without a workout "
            "would pass unenforced."
        )
        for state in states:
            _report(f"  {state.describe()}")
        _report(
            "\nRe-arm with:\n"
            "  systemctl --user daemon-reload\n"
            "  systemctl --user enable --now "
            + " ".join(state.name for state in disarmed)
        )
        return 1

    if not args.quiet:
        for state in states:
            _report(f"  {state.describe()}")
        _report("Screen locker enforcement is armed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
