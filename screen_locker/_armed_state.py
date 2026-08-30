"""Whether systemd would actually run the locker, read from systemd itself.

The 2026-08 outage was not a logic bug. Every predicate worked; the timer that
*invokes* them had been disabled by an ordering cycle, and nothing on the
machine considered that worth mentioning. ``systemctl status`` showed no failed
unit, because a job deleted to break a cycle is not a failure -- it is an
absence, and absences do not page anyone.

This module answers one question -- *would enforcement actually happen?* -- from
systemd's own view rather than from the unit files on disk, because the files
were correct-looking the entire time the timer sat disabled.

It lives in the package rather than in ``scripts/`` because two surfaces need
the same answer: ``scripts/check_enforcement_armed.py`` (the gate that rides
along with ``workout-sync.service``) and the Health view of the local web UI.
Two copies of this logic would be free to disagree about whether the locker is
alive, which is the failure it exists to detect.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import shutil
import subprocess

_logger = logging.getLogger(__name__)

# Every unit that must be armed for a workout-less day to end in a lock.
# The timers are what make enforcement recur.
REQUIRED_TIMERS = (
    "early-bird-workout-check.timer",
    "workout-locker.timer",
)

# workout-locker.service is WantedBy=graphical-session.target: a login
# one-shot that closes the window between a boot and the next timer tick.
# It is checked here because on 2026-08-30 it had silently drifted to
# `disabled`, the machine rebooted at 14:06, and nothing enforced until
# 14:30 -- while this very module reported "armed" the whole time, because
# it only ever looked at the two timers.
REQUIRED_SERVICES = ("workout-locker.service",)

# The target the login run hangs off. Checked as well as `is-enabled`
# because ~/.config/i3/config notes that i3 "does not reliably activate
# graphical-session.target" -- an enabled service anchored to an inactive
# target is exactly the correct-looking-but-disarmed state this module was
# written to catch.
_LOGIN_TARGET = "graphical-session.target"

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

        Returns:
            True when this timer would really fire.
        """
        return self.enabled and self.scheduled

    def describe(self) -> str:
        """Return a one-line human summary of this unit's state.

        Returns:
            An ``OK``/``DISARMED`` line naming every reason it is not armed.
        """
        if self.armed:
            return f"OK       {self.name}: {self._ready_phrase}"
        problems = []
        if not self.enabled:
            problems.append(f"not enabled (is-enabled={self.enabled_raw or 'unknown'})")
        if not self.scheduled:
            problems.append(self._missing_phrase)
        return f"DISARMED {self.name}: {', '.join(problems)}"

    @property
    def _ready_phrase(self) -> str:
        """Return the wording for an armed unit of this kind."""
        if self.name.endswith(".timer"):
            return "enabled and scheduled"
        return f"enabled and anchored to an active {_LOGIN_TARGET}"

    @property
    def _missing_phrase(self) -> str:
        """Return the wording for the not-scheduled half of this kind."""
        if self.name.endswith(".timer"):
            return "no next trigger in list-timers"
        return f"{_LOGIN_TARGET} is not active, so the login run cannot fire"


def systemctl_available() -> bool:
    """Return whether ``systemctl`` can be run at all.

    Reachable in containers and CI. Callers must treat False as "did not
    check", never as "checked and fine".

    Returns:
        True when ``systemctl`` is on PATH.
    """
    return shutil.which("systemctl") is not None


def _run(args: list[str]) -> tuple[int, str]:
    """Run ``args``, returning ``(returncode, stdout)``. Never raises.

    Args:
        args: The argument vector, passed without a shell.

    Returns:
        The process return code and its stdout; ``(1, "")`` if it could not run.
    """
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
    """Return the timer names systemd currently has a next trigger for.

    Returns:
        The subset of :data:`REQUIRED_TIMERS` with a scheduled next run.
    """
    _, out = _run(["systemctl", "--user", "list-timers", "--all", "--no-pager"])
    scheduled: set[str] = set()
    for line in out.splitlines():
        for name in REQUIRED_TIMERS:
            # A timer with no next trigger prints "n/a" in the NEXT column.
            if name in line and " n/a " not in f" {line} ":
                scheduled.add(name)
    return scheduled


LOCKER_UNIT = "workout-locker.service"


def locker_unit_active() -> bool | None:
    """Return whether the locker unit is running right now.

    "The lock would fire" is a statement about the *decision*; it says
    nothing about whether anything is currently enforcing it. On 2026-08-30
    the machine had rebooted, no locker process existed, and the status page
    read exactly the same as it does with a lock on screen.

    Returns:
        True/False, or None when systemd could not be asked -- which must
        never be rendered as "not running".
    """
    if not systemctl_available():
        return None
    code, out = _run(["systemctl", "--user", "is-active", LOCKER_UNIT])
    if code != 0 and not out.strip():
        return None
    return out.strip() == "active"


def _login_target_active() -> bool:
    """Return whether the target the login run hangs off is active.

    Returns:
        True when ``graphical-session.target`` is active.
    """
    code, out = _run(["systemctl", "--user", "is-active", _LOGIN_TARGET])
    return code == 0 and out.strip() == "active"


def collect_states() -> list[TimerState]:
    """Return the current arming state of every unit enforcement depends on.

    Returns:
        One :class:`TimerState` per entry in :data:`REQUIRED_TIMERS` and
        :data:`REQUIRED_SERVICES`.
    """
    scheduled = _scheduled_timers()
    login_target_up = _login_target_active()
    states = []
    for name in (*REQUIRED_TIMERS, *REQUIRED_SERVICES):
        code, out = _run(["systemctl", "--user", "is-enabled", name])
        raw = out.strip()
        states.append(
            TimerState(
                name=name,
                enabled=code == 0 and raw == "enabled",
                enabled_raw=raw,
                # For a timer this is "systemd has a next trigger for it";
                # for the login-run service it is "the target it is wanted by
                # is actually up". Both answer the same question: would this
                # unit really fire?
                scheduled=(
                    name in scheduled if name.endswith(".timer") else login_target_up
                ),
            )
        )
    return states
