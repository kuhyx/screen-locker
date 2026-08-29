"""Tests for _armed_state: is the locker actually schedulable.

The distinction these tests defend is the one that cost thirteen days in
2026-08: ``is-enabled`` says "enabled" for a timer whose job systemd deleted to
break an ordering cycle, so enabled alone is not armed.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from screen_locker._armed_state import (
    REQUIRED_TIMERS,
    TimerState,
    collect_states,
    systemctl_available,
)

_PKG = "screen_locker._armed_state"

_LISTED = """NEXT                        LEFT  LAST  PASSED UNIT
Sun 2026-08-30 08:30:00 CEST 10h   -     -      early-bird-workout-check.timer
Sat 2026-08-29 23:00:00 CEST 30min -     -      workout-locker.timer
"""


def _completed(stdout: str, code: int = 0) -> MagicMock:
    """Build a stand-in for a finished subprocess.

    Args:
        stdout: What the command printed.
        code: Its return code.

    Returns:
        An object with the two attributes ``_run`` reads.
    """
    proc = MagicMock()
    proc.returncode = code
    proc.stdout = stdout
    return proc


class TestTimerState:
    """armed is the conjunction; describe() names every missing half."""

    def test_enabled_and_scheduled_is_armed(self) -> None:
        """Both halves present means the timer will really fire."""
        state = TimerState("t", enabled=True, enabled_raw="enabled", scheduled=True)
        assert state.armed is True
        assert "OK" in state.describe()

    def test_enabled_but_unscheduled_is_not_armed(self) -> None:
        """The exact 2026-08 failure: enabled, but the job was deleted."""
        state = TimerState("t", enabled=True, enabled_raw="enabled", scheduled=False)
        assert state.armed is False
        assert "no next trigger" in state.describe()

    def test_scheduled_but_disabled_is_not_armed(self) -> None:
        """A transient start does not survive a reboot."""
        state = TimerState("t", enabled=False, enabled_raw="disabled", scheduled=True)
        assert state.armed is False
        assert "not enabled (is-enabled=disabled)" in state.describe()

    def test_unknown_enabled_state_is_named(self) -> None:
        """An empty is-enabled reads as unknown, not as a blank."""
        state = TimerState("t", enabled=False, enabled_raw="", scheduled=False)
        assert "is-enabled=unknown" in state.describe()


class TestSystemctlAvailable:
    """ "Could not check" must be distinguishable from "checked and fine"."""

    def test_present(self) -> None:
        """systemctl on PATH means the check can run."""
        with patch(f"{_PKG}.shutil.which", return_value="/usr/bin/systemctl"):
            assert systemctl_available() is True

    def test_absent(self) -> None:
        """No systemctl (containers, CI) is reported, never assumed fine."""
        with patch(f"{_PKG}.shutil.which", return_value=None):
            assert systemctl_available() is False


class TestCollectStates:
    """collect_states reads systemd's own view, not the unit files."""

    def test_all_armed(self) -> None:
        """Both timers enabled and listed with a next trigger."""
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(_LISTED),
                *[_completed("enabled\n") for _ in REQUIRED_TIMERS],
            ]
            states = collect_states()
        assert [s.name for s in states] == list(REQUIRED_TIMERS)
        assert all(s.armed for s in states)

    def test_timer_listed_with_no_next_trigger_is_unscheduled(self) -> None:
        """An "n/a" NEXT column means systemd will never run it."""
        listed = (
            "NEXT LEFT LAST PASSED UNIT\n n/a  -   -    -      workout-locker.timer\n"
        )
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(listed),
                *[_completed("enabled\n") for _ in REQUIRED_TIMERS],
            ]
            states = collect_states()
        assert all(not s.scheduled for s in states)

    def test_disabled_timer_is_reported(self) -> None:
        """A non-zero is-enabled marks the timer disabled."""
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(_LISTED),
                *[_completed("disabled\n", code=1) for _ in REQUIRED_TIMERS],
            ]
            states = collect_states()
        assert all(not s.enabled for s in states)

    def test_a_check_that_cannot_run_is_not_a_pass(self) -> None:
        """When systemctl cannot be executed, nothing reads as armed."""
        with patch(f"{_PKG}.subprocess.run", side_effect=OSError("no exec")):
            states = collect_states()
        assert all(not s.armed for s in states)

    def test_a_timeout_is_not_a_pass_either(self) -> None:
        """A hung systemctl must fail closed, same as a missing one."""
        with patch(
            f"{_PKG}.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="systemctl", timeout=10),
        ):
            states = collect_states()
        assert all(not s.armed for s in states)
