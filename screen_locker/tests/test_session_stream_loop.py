"""Tests for _session_stream.run_forever: reconnect backoff and thread control."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from screen_locker import _session_stream
from screen_locker.tests.test_session_stream import make_stream

if TYPE_CHECKING:
    from screen_locker._session_stream import SessionStream

_LONG = 400.0  # longer than the 300 s minimum lifetime


@pytest.fixture
def stream(monkeypatch: pytest.MonkeyPatch) -> SessionStream:
    """A ``SessionStream`` that never reads or writes the real device id."""
    return make_stream(monkeypatch)


class _Loop:
    """Scripted ``_run_one`` outcomes with a fake clock, jitter and stop event."""

    def __init__(
        self,
        stream: SessionStream,
        monkeypatch: pytest.MonkeyPatch,
        script: list[tuple[bool, float, bool]],
        factor: float = 1.0,
    ) -> None:
        self.script = script
        self.index = 0
        self.now = 0.0
        self.waits: list[float] = []
        self.uniform_args: list[tuple[float, float]] = []
        self.factor = factor
        self.stream = stream
        monkeypatch.setattr(stream, "_run_one", self._run_one)
        monkeypatch.setattr(stream, "_stop", self)
        monkeypatch.setattr(
            _session_stream, "time", SimpleNamespace(monotonic=lambda: self.now)
        )
        monkeypatch.setattr(_session_stream, "_JITTER", self)

    def _run_one(self) -> bool:
        planned, duration, snapshot = self.script[self.index]
        self.index += 1
        self.now += duration
        self.stream._got_snapshot = snapshot
        return planned

    def is_set(self) -> bool:
        """Stop once the script is exhausted."""
        return self.index >= len(self.script)

    def wait(self, pause: float) -> None:
        """Record the backoff instead of sleeping."""
        self.waits.append(pause)

    def uniform(self, low: float, high: float) -> float:
        """Record the jitter range; scale between the bounds by ``factor``."""
        self.uniform_args.append((low, high))
        return low + (high - low) * self.factor


class TestRunForever:
    """Reconnect backoff: growth, cap, reset and the tight-loop guard."""

    @staticmethod
    def _run(loop: _Loop) -> list[float]:
        loop.stream.run_forever()
        return loop.waits

    def test_backoff_doubles_and_is_capped(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """1, 2, 4 ... capped at 60 s while connections keep failing fast."""
        loop = _Loop(stream, monkeypatch, [(False, 0.0, False)] * 8)
        assert self._run(loop) == [1, 2, 4, 8, 16, 32, 60, 60]

    def test_pause_is_jittered_between_half_and_full(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pause is the delay times a factor drawn from 0.5..1.0."""
        loop = _Loop(stream, monkeypatch, [(False, 0.0, False)] * 2, factor=0.0)
        assert self._run(loop) == [0.5, 1.0]
        assert set(loop.uniform_args) == {(0.5, 1.0)}

    def test_long_lived_connection_with_snapshot_resets_the_backoff(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A healthy connection (snapshot + 5 min) restarts the ladder at 1 s."""
        script = [(False, 0.0, False)] * 3 + [(False, _LONG, True), (False, 0.0, False)]
        assert self._run(_Loop(stream, monkeypatch, script)) == [1, 2, 4, 1, 2]

    def test_long_connection_without_snapshot_does_not_reset(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Surviving 5 min without ever getting data proves nothing."""
        script = [(False, 0.0, False)] * 3 + [(False, _LONG, False)]
        assert self._run(_Loop(stream, monkeypatch, script)) == [1, 2, 4, 8]

    def test_short_snapshot_connection_does_not_reset(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A snapshot that dies within 5 min is a flapping link: keep backing off."""
        script = [(False, 0.0, False)] * 2 + [(False, 5.0, True)]
        assert self._run(_Loop(stream, monkeypatch, script)) == [1, 2, 4]

    def test_planned_end_after_a_long_life_reconnects_at_once(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Token renewal after a healthy hour is not a failure: no pause."""
        script: list[tuple[bool, float, bool]] = [(True, 3600.0, True)] * 2
        assert self._run(_Loop(stream, monkeypatch, script)) == []

    def test_planned_end_after_a_short_life_still_backs_off(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """auth_revoked straight after connecting must not spin in a tight loop."""
        script: list[tuple[bool, float, bool]] = [(True, 1.0, True)] * 3
        assert self._run(_Loop(stream, monkeypatch, script)) == [1, 2, 4]

    def test_each_pause_is_logged_as_a_warning(
        self,
        stream: SessionStream,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Reconnect pauses are visible in the journal."""
        loop = _Loop(stream, monkeypatch, [(False, 0.0, False)])
        with caplog.at_level(logging.WARNING):
            self._run(loop)
        (record,) = caplog.records
        assert record.levelno == logging.WARNING
        assert record.getMessage() == "Reconnecting the session stream in 1.0 s"

    def test_stop_before_start_runs_nothing(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A set stop flag exits without connecting."""
        loop = _Loop(stream, monkeypatch, [])
        stream.run_forever()
        assert loop.index == 0


class TestThread:
    """start() and stop()."""

    def test_start_runs_the_loop_on_a_named_daemon_thread(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The loop runs off the caller's thread, as a daemon."""
        ran: list[str] = []
        monkeypatch.setattr(stream, "run_forever", lambda: ran.append("ran"))
        thread = stream.start()
        thread.join(timeout=5)
        assert ran == ["ran"]
        assert thread.daemon is True
        assert thread.name == "firebase-session-stream"

    def test_stop_sets_the_flag(self, stream: SessionStream) -> None:
        """stop() asks the loop to exit after the current connection."""
        assert stream._stop.is_set() is False
        stream.stop()
        assert stream._stop.is_set() is True
