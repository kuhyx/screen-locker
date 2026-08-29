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
from dataclasses import dataclass
import logging
import shutil
import subprocess
import sys

_logger = logging.getLogger(__name__)

# Every unit that must be armed for a workout-less day to end in a lock.
# workout-locker.service itself is WantedBy=graphical-session.target and so is
# only ever a login one-shot; the timers are what make enforcement recur.
REQUIRED_TIMERS = (
    "early-bird-workout-check.timer",
    "workout-locker.timer",
)

_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class TimerState:
    """What systemd currently believes about one timer."""

    name: str
    enabled: bool
    enabled_raw: str
    scheduled: bool

    @property
    def armed(self) -> bool:
        """True only when the timer is both enabled and actually scheduled.

        Both halves matter. ``is-enabled`` alone passes for a timer whose job
        systemd deleted to break an ordering cycle; ``list-timers`` alone passes
        for a transient ``start``ed timer that will not survive a reboot.
        """
        return self.enabled and self.scheduled

    def describe(self) -> str:
        """Return a one-line human summary of this timer's state."""
        if self.armed:
            return f"OK       {self.name}: enabled and scheduled"
        problems = []
        if not self.enabled:
            problems.append(f"not enabled (is-enabled={self.enabled_raw or 'unknown'})")
        if not self.scheduled:
            problems.append("no next trigger in list-timers")
        return f"DISARMED {self.name}: {', '.join(problems)}"


def _report(message: str) -> None:
    """Write one line to stderr, so a disarmed locker is visible in the unit."""
    sys.stderr.write(f"{message}\n")


def _run(args: list[str]) -> tuple[int, str]:
    """Run ``args``, returning (returncode, stdout). Never raises."""
    try:
        # Explicit argument list, never shell=True.
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        # A check that cannot run must not look like a check that passed.
        _logger.exception("Could not run %s", " ".join(args))
        return 1, ""
    return proc.returncode, proc.stdout


def _scheduled_timers() -> set[str]:
    """Return the timer names systemd currently has a next trigger for."""
    _, out = _run(["systemctl", "--user", "list-timers", "--all", "--no-pager"])
    scheduled: set[str] = set()
    for line in out.splitlines():
        for name in REQUIRED_TIMERS:
            # A timer with no next trigger prints "n/a" in the NEXT column.
            if name in line and " n/a " not in f" {line} ":
                scheduled.add(name)
    return scheduled


def collect_states() -> list[TimerState]:
    """Return the current arming state of every required timer."""
    scheduled = _scheduled_timers()
    states = []
    for name in REQUIRED_TIMERS:
        code, out = _run(["systemctl", "--user", "is-enabled", name])
        raw = out.strip()
        states.append(
            TimerState(
                name=name,
                enabled=code == 0 and raw == "enabled",
                enabled_raw=raw,
                scheduled=name in scheduled,
            )
        )
    return states


def main(argv: list[str] | None = None) -> int:
    """Report arming state; return 1 when enforcement would not happen."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only when something is wrong",
    )
    args = parser.parse_args(argv)

    if shutil.which("systemctl") is None:
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
