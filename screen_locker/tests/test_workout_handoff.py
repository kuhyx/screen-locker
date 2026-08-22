"""Tests for lending the lock screen's grab to the workout app.

The invariant: the grab moves, nothing else does. VT switching stays disabled
and the arbiter claim stays held, because ``close()`` would undo both and hand
the user Ctrl+Alt+F2 out of the obligation the lock exists to enforce.
"""

from __future__ import annotations

import tkinter as tk

from screen_locker._workout_handoff import lock_grab_handoff, start_workout


class _FakeRecovery:
    """Stands in for gatelock's watchdog, which re-grabs every 1000ms."""

    def __init__(self) -> None:
        self.running = True
        self.events: list[str] = []

    def stop(self) -> None:
        self.running = False
        self.events.append("stop")


class _FakeLock:
    """A lock window that records the order of grab operations."""

    def __init__(self, *, release_raises: bool = False) -> None:
        self._recovery = _FakeRecovery()
        self.events: list[str] = []
        self.closed = False
        self._release_raises = release_raises
        outer = self

        class _Root:
            def grab_release(self) -> None:
                outer.events.append("grab_release")
                if outer._release_raises:
                    msg = "no grab to release"
                    raise tk.TclError(msg)

        self.root = _Root()

    def grab_input(self) -> None:
        self.events.append("grab_input")
        self._recovery.running = True

    def close(self) -> None:
        self.closed = True


class TestLockGrabHandoff:
    """Releasing and re-taking, in the only safe order."""

    def test_stops_the_watchdog_before_releasing(self) -> None:
        """A tick between release and the app's own grab would steal it back."""
        lock = _FakeLock()
        lock_grab_handoff(lock).release()
        assert lock._recovery.events == ["stop"]
        assert lock.events == ["grab_release"]
        assert not lock._recovery.running

    def test_reacquire_restores_the_grab_and_the_watchdog(self) -> None:
        handoff = lock_grab_handoff(lock := _FakeLock())
        handoff.release()
        handoff.reacquire()
        assert lock.events == ["grab_release", "grab_input"]
        assert lock._recovery.running

    def test_never_closes_the_lock_window(self) -> None:
        """close() also restores VT switching -- that is the escape hatch."""
        handoff = lock_grab_handoff(lock := _FakeLock())
        handoff.release()
        handoff.reacquire()
        assert not lock.closed

    def test_tolerates_having_no_grab_to_release(self) -> None:
        """Tk raises when releasing a grab we do not hold; not fatal."""
        handoff = lock_grab_handoff(lock := _FakeLock(release_raises=True))
        handoff.release()
        handoff.reacquire()
        assert lock.events == ["grab_release", "grab_input"]


class TestStartWorkout:
    """The button handler never raises onto a screen with no way out."""

    def test_reports_a_failed_launch_as_a_message(self, monkeypatch: object) -> None:
        from screen_locker import _workout_handoff

        class _Result:
            launched = False
            reason = "not built"

        monkeypatch.setattr(
            _workout_handoff, "launch_workout_app", lambda _h: _Result()
        )
        message = start_workout(_FakeLock())
        assert "Could not start the workout" in message
        assert "not built" in message

    def test_reports_a_finished_run(self, monkeypatch: object) -> None:
        from screen_locker import _workout_handoff

        class _Result:
            launched = True
            reason = "exited with code 0"

        monkeypatch.setattr(
            _workout_handoff, "launch_workout_app", lambda _h: _Result()
        )
        assert "checking whether it counted" in start_workout(_FakeLock())
