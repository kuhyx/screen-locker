"""Tests for _armed_state: is the locker actually schedulable.

The distinction these tests defend is the one that cost thirteen days in
2026-08: ``is-enabled`` says "enabled" for a timer whose job systemd deleted to
break an ordering cycle, so enabled alone is not armed.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from screen_locker._armed_state import (
    REQUIRED_SERVICES,
    REQUIRED_TIMERS,
    TimerState,
    collect_states,
    locker_unit_active,
    systemctl_available,
)

_ALL_UNITS = (*REQUIRED_TIMERS, *REQUIRED_SERVICES)
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
        state = TimerState(
            "t.timer", enabled=True, enabled_raw="enabled", scheduled=True
        )
        assert state.armed is True
        assert "OK" in state.describe()

    def test_enabled_but_unscheduled_is_not_armed(self) -> None:
        """The exact 2026-08 failure: enabled, but the job was deleted."""
        state = TimerState(
            "t.timer", enabled=True, enabled_raw="enabled", scheduled=False
        )
        assert state.armed is False
        assert "no next trigger" in state.describe()

    def test_scheduled_but_disabled_is_not_armed(self) -> None:
        """A transient start does not survive a reboot."""
        state = TimerState(
            "t.timer", enabled=False, enabled_raw="disabled", scheduled=True
        )
        assert state.armed is False
        assert "not enabled (is-enabled=disabled)" in state.describe()

    def test_unknown_enabled_state_is_named(self) -> None:
        """An empty is-enabled reads as unknown, not as a blank."""
        state = TimerState("t.timer", enabled=False, enabled_raw="", scheduled=False)
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
        """Every timer enabled and listed, and the login run anchored."""
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(_LISTED),
                _completed("active\n"),
                *[_completed("enabled\n") for _ in _ALL_UNITS],
            ]
            states = collect_states()
        assert [s.name for s in states] == list(_ALL_UNITS)
        assert all(s.armed for s in states)

    def test_the_login_run_is_checked_too(self) -> None:
        """The 2026-08-30 gap: timers fine, login run silently disabled.

        Enforcement read "armed" through a 24-minute unenforced window
        because only the timers were ever looked at.
        """
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(_LISTED),
                _completed("active\n"),
                *[_completed("enabled\n") for _ in REQUIRED_TIMERS],
                _completed("disabled\n", code=1),
            ]
            states = collect_states()
        service = states[-1]
        assert service.name == REQUIRED_SERVICES[0]
        assert service.armed is False
        assert not all(s.armed for s in states)

    def test_an_inactive_login_target_disarms_the_service(self) -> None:
        """Enabled is not enough: i3 may never activate the target."""
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(_LISTED),
                _completed("inactive\n", code=3),
                *[_completed("enabled\n") for _ in _ALL_UNITS],
            ]
            states = collect_states()
        service = states[-1]
        assert service.enabled is True
        assert service.armed is False
        assert "is not active" in service.describe()

    def test_timer_listed_with_no_next_trigger_is_unscheduled(self) -> None:
        """An "n/a" NEXT column means systemd will never run it."""
        listed = (
            "NEXT LEFT LAST PASSED UNIT\n n/a  -   -    -      workout-locker.timer\n"
        )
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(listed),
                _completed("inactive\n", code=3),
                *[_completed("enabled\n") for _ in _ALL_UNITS],
            ]
            states = collect_states()
        assert all(not s.scheduled for s in states)

    def test_disabled_timer_is_reported(self) -> None:
        """A non-zero is-enabled marks the timer disabled."""
        with patch(f"{_PKG}.subprocess.run") as run:
            run.side_effect = [
                _completed(_LISTED),
                _completed("active\n"),
                *[_completed("disabled\n", code=1) for _ in _ALL_UNITS],
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


class TestLockerUnitActive:
    """ "Would lock" says nothing about whether anything is enforcing it."""

    def test_an_active_unit_reads_as_running(self) -> None:
        """The ordinary case while a lock is up."""
        with patch(f"{_PKG}.subprocess.run", return_value=_completed("active\n")):
            assert locker_unit_active() is True

    def test_an_inactive_unit_reads_as_not_running(self) -> None:
        """The 2026-08-30 screenshot: decided to lock, nothing running."""
        with patch(
            f"{_PKG}.subprocess.run", return_value=_completed("inactive\n", code=3)
        ):
            assert locker_unit_active() is False

    def test_no_systemctl_is_unknown_not_false(self) -> None:
        """ "Could not ask" must never render as "not running"."""
        with patch(f"{_PKG}.shutil.which", return_value=None):
            assert locker_unit_active() is None

    def test_a_failed_probe_is_unknown_not_false(self) -> None:
        """A systemctl that cannot run answers nothing, not "no"."""
        with patch(f"{_PKG}.subprocess.run", side_effect=OSError("no exec")):
            assert locker_unit_active() is None

    def test_an_armed_login_run_says_what_anchors_it(self) -> None:
        """The Health row must name the target, since that is what drifts."""
        state = TimerState(
            REQUIRED_SERVICES[0], enabled=True, enabled_raw="enabled", scheduled=True
        )
        assert state.armed is True
        assert "graphical-session.target" in state.describe()
