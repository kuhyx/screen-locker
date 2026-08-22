"""Tests for supervising the desktop workout app as the lock surface.

The invariant every test here defends: the X grab is released ONLY once the
app has signalled that its own fullscreen window is up. Releasing it to an app
that never started would leave the machine unlocked with the obligation unmet.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from screen_locker._workout_app import (
    READY_MARKER,
    GrabHandoff,
    ProcessHooks,
    WorkoutAppResult,
    launch_workout_app,
    workout_app_binary,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class _FakeStdout:
    """A pipe that yields fixed lines, then EOF."""

    def __init__(self, lines: Sequence[str]) -> None:
        self._it = iter(lines)

    def readline(self) -> str:
        return next(self._it, "")


class _FakeChild:
    """A stand-in for the Flutter process."""

    def __init__(self, lines: Sequence[str], *, returncode: int = 0) -> None:
        self.stdout = _FakeStdout(lines)
        self.returncode = returncode
        self.terminated = False
        self.waited = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self) -> int:
        self.waited = True
        return self.returncode


class _Recorder:
    """Records grab release/reacquire in call order."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def release(self) -> None:
        self.calls.append("release")

    def reacquire(self) -> None:
        self.calls.append("reacquire")


def _always_readable(
    rlist: object, _w: object, _x: object, _t: float
) -> tuple[object, list[object], list[object]]:
    """Stand in for select(): the fake pipe is always ready to read."""
    return rlist, [], []


def _run(
    lines: Sequence[str],
    recorder: _Recorder,
    *,
    child: _FakeChild | None = None,
    **kwargs: object,
) -> object:
    kid = child if child is not None else _FakeChild(lines)
    return launch_workout_app(
        GrabHandoff(release=recorder.release, reacquire=recorder.reacquire),
        binary=Path("/nonexistent/workout_app"),
        hooks=ProcessHooks(popen=lambda *_a, **_k: kid, selector=_always_readable),
        **kwargs,
    )


class TestLaunchWorkoutApp:
    """The handoff, and every way it can fail safely."""

    def test_releases_the_grab_once_the_app_is_ready(self) -> None:
        recorder = _Recorder()
        result = _run([f"{READY_MARKER}\n"], recorder)
        assert result.launched
        assert recorder.calls == ["release", "reacquire"]

    def test_tolerates_output_before_the_ready_line(self) -> None:
        """Flutter prints Mesa/Impeller noise before anything of ours."""
        recorder = _Recorder()
        result = _run(["MESA-EGL: warning\n", f"{READY_MARKER}\n"], recorder)
        assert result.launched
        assert "release" in recorder.calls

    def test_never_releases_when_the_app_dies_before_ready(self) -> None:
        """The invariant: a dead app must not be handed the screen."""
        recorder = _Recorder()
        result = _run([], recorder)
        assert not result.launched
        assert "release" not in recorder.calls
        assert "exited before signalling ready" in result.reason

    def test_terminates_an_app_that_never_signals_ready(self) -> None:
        recorder = _Recorder()
        child = _FakeChild([])
        _run([], recorder, child=child)
        assert child.terminated

    def test_reports_a_hang_differently_from_a_crash(self) -> None:
        """A slow first sync and a broken build need different fixes."""
        recorder = _Recorder()
        # Never EOFs and never readies: readline keeps returning noise.
        child = _FakeChild(["noise\n"] * 10_000)
        result = _run([], recorder, child=child, ready_timeout=0.0)
        assert not result.launched
        assert "never signalled ready" in result.reason
        assert "release" not in recorder.calls

    def test_times_out_on_an_app_that_starts_but_prints_nothing(self) -> None:
        """The regression: a silent live app must not hold the lock forever.

        ``readline()`` on a real pipe blocks, so the timeout can only be
        enforced by waiting on the pipe rather than polling the clock.
        """
        recorder = _Recorder()
        child = _FakeChild([])

        def _never_readable(
            _r: object, _w: object, _x: object, _t: float
        ) -> tuple[list[object], list[object], list[object]]:
            return [], [], []

        result = launch_workout_app(
            GrabHandoff(release=recorder.release, reacquire=recorder.reacquire),
            binary=Path("/nonexistent/workout_app"),
            hooks=ProcessHooks(popen=lambda *_a, **_k: child, selector=_never_readable),
            ready_timeout=5.0,
        )
        assert not result.launched
        assert "never signalled ready" in result.reason
        assert "release" not in recorder.calls
        assert child.terminated

    def test_reacquires_the_grab_even_when_the_app_crashes(self) -> None:
        """However the app exits, something must hold the screen after."""
        recorder = _Recorder()
        child = _FakeChild([f"{READY_MARKER}\n"], returncode=-15)
        result = _run([], recorder, child=child)
        assert recorder.calls == ["release", "reacquire"]
        assert "-15" in result.reason

    def test_waits_for_the_app_to_exit(self) -> None:
        recorder = _Recorder()
        child = _FakeChild([f"{READY_MARKER}\n"])
        _run([], recorder, child=child)
        assert child.waited

    def test_treats_a_missing_stdout_pipe_as_a_dead_app(self) -> None:
        """No pipe means no ready line can ever arrive -- never release."""
        recorder = _Recorder()
        child = _FakeChild([])
        child.stdout = None
        result = _run([], recorder, child=child)
        assert not result.launched
        assert "release" not in recorder.calls
        assert child.terminated

    def test_says_so_when_the_app_is_not_built(self) -> None:
        recorder = _Recorder()
        result = launch_workout_app(
            GrabHandoff(release=recorder.release, reacquire=recorder.reacquire),
            resolve_binary=lambda: None,
            hooks=ProcessHooks(
                popen=lambda *_a, **_k: _FakeChild([]), selector=_always_readable
            ),
        )
        assert not result.launched
        assert "not built" in result.reason
        assert recorder.calls == []


class TestWorkoutAppBinary:
    """Locating the built bundle."""

    def test_returns_none_when_nothing_is_built(self, tmp_path: Path) -> None:
        assert workout_app_binary(tmp_path) is None

    def test_defaults_to_the_real_repo_root(self) -> None:
        """The no-argument call is what the lock screen actually uses."""
        found = workout_app_binary()
        assert found is None or found.name == "workout_app"

    def test_prefers_release_over_debug(self, tmp_path: Path) -> None:
        base = tmp_path / "stronglift_replacement/workout_app/build/linux/x64"
        for flavour in ("debug", "release"):
            binary = base / flavour / "bundle" / "workout_app"
            binary.parent.mkdir(parents=True)
            binary.touch()
        assert workout_app_binary(tmp_path).parent.parent.name == "release"

    def test_falls_back_to_debug(self, tmp_path: Path) -> None:
        binary = (
            tmp_path
            / "stronglift_replacement/workout_app/build/linux/x64/debug/bundle"
            / "workout_app"
        )
        binary.parent.mkdir(parents=True)
        binary.touch()
        assert workout_app_binary(tmp_path) == binary


class TestWorkoutAppResult:
    """The result carries a reason a human can act on."""

    def test_repr_shows_the_outcome_and_reason(self) -> None:
        """Logged on failure paths, so it must name why, not just False."""
        result = WorkoutAppResult(launched=False, reason="not built")
        assert "launched=False" in repr(result)
        assert "not built" in repr(result)
