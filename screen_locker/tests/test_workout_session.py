"""Tests for running the workout app without freezing the lock's event loop.

The invariant these defend: no phase blocks. Every wait is an ``after``
callback, because a blocked event loop makes the lock's own escapes inert --
which is what once forced a hard reboot out of a "safe" demo.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from screen_locker._workout_app import GrabHandoff, ProcessHooks
from screen_locker._workout_ready import READY_MARKER
from screen_locker._workout_session import WorkoutSession

if TYPE_CHECKING:
    from collections.abc import Callable


class _FakeAfter:
    """A drainable stand-in for ``root.after``."""

    def __init__(self) -> None:
        self.queue: list[Callable[[], None]] = []

    def __call__(self, _ms: int, callback: Callable[[], None]) -> object:
        self.queue.append(callback)
        return object()

    def drain(self, limit: int = 5000) -> None:
        for _ in range(limit):
            if not self.queue:
                return
            self.queue.pop(0)()


class _FakeStdout:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def readline(self) -> str:
        return self._chunks.pop(0) if self._chunks else ""


class _FakeChild:
    def __init__(self, chunks: list[str], *, exits_after: int = 1) -> None:
        self.stdout = _FakeStdout(chunks)
        self.returncode: int | None = None
        self.terminated = False
        self._polls = 0
        self._exits_after = exits_after

    def poll(self) -> int | None:
        self._polls += 1
        if self._polls >= self._exits_after:
            self.returncode = 0
            return 0
        return None

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15


def _session(child: _FakeChild, after: _FakeAfter, calls: list[str]):
    return WorkoutSession(
        GrabHandoff(
            release=lambda: calls.append("release"),
            reacquire=lambda: calls.append("reacquire"),
        ),
        after=after,
        on_status=lambda text: calls.append(f"status:{text[:20]}"),
        binary=Path("/nonexistent/workout_app"),
        hooks=ProcessHooks(
            popen=lambda *_a, **_k: child,
            selector=lambda r, _w, _x, _t: (r, [], []),
        ),
    )


class TestWorkoutSession:
    """Each phase hands control back to the event loop."""

    def test_releases_the_grab_only_after_the_ready_line(self) -> None:
        after, calls = _FakeAfter(), []
        child = _FakeChild([f"{READY_MARKER}\n"], exits_after=2)
        _session(child, after, calls).start()
        assert "release" not in calls  # nothing released synchronously
        after.drain()
        assert "release" in calls
        assert calls.index("release") < calls.index("reacquire")

    def test_never_releases_when_the_app_dies_before_ready(self) -> None:
        after, calls = _FakeAfter(), []
        _session(_FakeChild([]), after, calls).start()
        after.drain()
        assert "release" not in calls

    def test_reacquires_when_the_app_exits(self) -> None:
        after, calls = _FakeAfter(), []
        child = _FakeChild([f"{READY_MARKER}\n"], exits_after=3)
        _session(child, after, calls).start()
        after.drain()
        assert calls[-2] == "reacquire"
        assert "Workout app closed" in calls[-1]

    def test_abort_terminates_the_app_and_restores_the_lock(self) -> None:
        """The escape hatch: usable at any point, from outside X."""
        after, calls = _FakeAfter(), []
        child = _FakeChild([f"{READY_MARKER}\n"], exits_after=99)
        session = _session(child, after, calls)
        session.start()
        for _ in range(3):
            if after.queue:
                after.queue.pop(0)()
        session.abort()
        assert child.terminated
        assert "reacquire" in calls

    def test_abort_before_release_does_not_reacquire(self) -> None:
        """Nothing was lent, so there is nothing to take back."""
        after, calls = _FakeAfter(), []
        session = _session(_FakeChild([], exits_after=99), after, calls)
        session.start()
        session.abort()
        assert "reacquire" not in calls

    def test_times_out_without_ever_blocking(self) -> None:
        after, calls = _FakeAfter(), []
        child = _FakeChild(["noise\n"] * 10, exits_after=99)
        session = _session(child, after, calls)
        session._remaining = 3
        session.start()
        after.drain()
        assert child.terminated
        assert "release" not in calls

    def test_says_so_when_the_app_is_not_built(self) -> None:
        after, calls = _FakeAfter(), []
        session = WorkoutSession(
            GrabHandoff(release=lambda: None, reacquire=lambda: None),
            after=after,
            on_status=calls.append,
            hooks=ProcessHooks(popen=lambda *_a, **_k: None),
        )
        # Force the unbuilt case regardless of what this machine has built.
        session._binary = None
        monkey = "screen_locker._workout_session.workout_app_binary"
        import unittest.mock

        with unittest.mock.patch(monkey, return_value=None):
            session.start()
        assert any("not built" in c for c in calls)

    def test_handles_a_missing_stdout_pipe(self) -> None:
        after, calls = _FakeAfter(), []
        child = _FakeChild([])
        child.stdout = None
        _session(child, after, calls).start()
        after.drain()
        assert "release" not in calls


class TestSessionEdges:
    """Paths a fake pipe or a happy path does not reach."""

    def test_keeps_waiting_when_the_pipe_has_nothing_yet(self) -> None:
        """A quiet app is not a dead app; poll again, never block."""
        after, calls = _FakeAfter(), []
        child = _FakeChild([f"{READY_MARKER}\n"], exits_after=99)
        session = WorkoutSession(
            GrabHandoff(
                release=lambda: calls.append("release"),
                reacquire=lambda: calls.append("reacquire"),
            ),
            after=after,
            on_status=lambda _t: None,
            binary=Path("/nonexistent/workout_app"),
            hooks=ProcessHooks(
                popen=lambda *_a, **_k: child,
                # Never readable: the app is up but silent.
                selector=lambda _r, _w, _x, _t: ([], [], []),
            ),
        )
        session._remaining = 2
        session.start()
        after.drain()
        assert "release" not in calls
        assert child.terminated

    def test_abort_with_no_child_is_harmless(self) -> None:
        after, calls = _FakeAfter(), []
        session = _session(_FakeChild([]), after, calls)
        session.abort()  # never started
        assert len(calls) == 1
        assert "Workout app closed" in calls[0]

    def test_reads_a_real_pipe_without_waiting_for_a_newline(self) -> None:
        """The production path: a text stream wrapping a binary buffer."""
        import os

        from screen_locker._workout_session import _read_available

        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, "r") as reader, os.fdopen(write_fd, "w") as writer:
            writer.write("WORKOUT_")
            writer.flush()
            assert _read_available(reader) == "WORKOUT_"


class TestDemoEscapeFlag:
    """The flag that arms the app's own escape hatch."""

    def _argv_for(self, *, demo_escape: bool) -> list[str]:
        seen: list[list[str]] = []

        def _popen(argv: list[str], **_kwargs: object) -> _FakeChild:
            seen.append(argv)
            return _FakeChild([])

        WorkoutSession(
            GrabHandoff(release=lambda: None, reacquire=lambda: None),
            after=_FakeAfter(),
            on_status=lambda _t: None,
            binary=Path("/nonexistent/workout_app"),
            hooks=ProcessHooks(popen=_popen, demo_escape=demo_escape),
        ).start()
        return seen[0]

    def test_production_never_arms_the_hatch(self) -> None:
        """The default must not hand the user a way out of a real lock."""
        assert "--demo-escape" not in self._argv_for(demo_escape=False)

    def test_demo_arms_the_hatch(self) -> None:
        argv = self._argv_for(demo_escape=True)
        assert argv[-1] == "--demo-escape"
        assert "--lock-mode" in argv
