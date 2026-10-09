"""Tests for _session_stream: connecting, backoff, reconnect and thread control."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging

import pytest
import requests

from screen_locker import _session_stream
from screen_locker._rtdb_stream import SseEvent
from screen_locker._session_stream import SessionStream, _ByteMeter
from screen_locker._stream_auth import StreamAuth, StreamError
from screen_locker.tests.test_session_stream import fake_response, make_stream

_RENEW = datetime(2999, 1, 1, tzinfo=UTC)
_LONG = 400.0  # longer than the 300 s minimum lifetime


@pytest.fixture
def stream(monkeypatch: pytest.MonkeyPatch) -> SessionStream:
    """A ``SessionStream`` that never reads or writes the real device id."""
    return make_stream(monkeypatch)


class TestByteMeter:
    """Line splitting without waiting for a full buffer."""

    def test_lines_split_across_chunks_and_counted(self) -> None:
        """A line broken over two reads is rejoined; CRLF is stripped."""
        meter = _ByteMeter()
        chunks = [b"ev", b"ent: a\r\ndata: b\n\nx", b"y\n"]
        lines = list(meter.lines(fake_response(chunks)))
        assert lines == ["event: a", "data: b", "", "xy"]
        assert meter.total == sum(map(len, chunks))

    def test_trailing_partial_line_is_dropped_at_eof(self) -> None:
        """Bytes after the last newline never form a line."""
        meter = _ByteMeter()
        assert list(meter.lines(fake_response([b"a\nb"]))) == ["a"]


class TestDispatch:
    """One put/patch handed to the cache."""

    def test_undecodable_event_is_warned_and_does_not_end_the_stream(
        self, stream: SessionStream, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed data logs a WARNING naming the fallback, never raises."""
        with caplog.at_level(logging.WARNING):
            stream._dispatch(SseEvent("put", "{garbage"), 10)
            stream._dispatch(SseEvent("patch", "[]"), 10)
        messages = [r.getMessage() for r in caplog.records]
        assert len(messages) == 2
        assert all("undecodable" in m and "15-min workout-sync" in m for m in messages)
        assert stream._got_snapshot is False

    def test_snapshot_flag_only_set_by_snapshots(
        self, stream: SessionStream, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A patch does not mark the connection as having a snapshot."""
        patch_event = SseEvent("patch", json.dumps({"path": "/", "data": {}}))
        with caplog.at_level(logging.INFO):
            stream._dispatch(patch_event, 7)
        assert stream._got_snapshot is False
        assert any(
            "Session stream patch (7 bytes" in r.getMessage() for r in caplog.records
        )
        snapshot = SseEvent("put", json.dumps({"path": "/", "data": None}))
        with caplog.at_level(logging.INFO):
            stream._dispatch(snapshot, 9)
        assert stream._got_snapshot is True
        assert any(
            "Session stream snapshot (9 bytes" in r.getMessage() for r in caplog.records
        )


class _FakeHttp:
    """``requests.Session`` stand-in recording the one GET it is given."""

    def __init__(self, outcome: requests.Response | Exception) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> requests.Response:
        """Record the request; return or raise the scripted outcome."""
        self.calls.append((url, kwargs))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _arm(
    stream: SessionStream,
    monkeypatch: pytest.MonkeyPatch,
    outcome: requests.Response | Exception,
) -> _FakeHttp:
    """Give ``stream`` a canned auth and HTTP layer."""
    auth = StreamAuth("https://db/x.json", "TOK", _RENEW)
    monkeypatch.setattr(_session_stream, "stream_auth", lambda _path: auth)
    http = _FakeHttp(outcome)
    monkeypatch.setattr(stream, "_http", http)
    return http


class TestConnectOnce:
    """Opening the connection and classifying HTTP failures."""

    def test_streams_with_token_and_sse_headers(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 200 is consumed with the auth's renew deadline, then released."""
        response = fake_response()
        http = _arm(stream, monkeypatch, response)
        consumed: list[tuple[requests.Response, datetime]] = []
        monkeypatch.setattr(
            stream, "_consume", lambda resp, renew: consumed.append((resp, renew))
        )
        stream._connect_once()
        url, kwargs = http.calls[0]
        assert url == "https://db/x.json"
        assert kwargs["params"] == {"auth": "TOK"}
        assert kwargs["headers"] == {"Accept": "text/event-stream"}
        assert kwargs["stream"] is True
        assert kwargs["timeout"] == (10, 90)
        assert consumed == [(response, _RENEW)]
        assert response.raw.closed is True

    @pytest.mark.parametrize(
        "error",
        [requests.ConnectionError("refused"), TimeoutError("connect timed out")],
    )
    def test_network_error_opening_is_a_stream_error(
        self,
        stream: SessionStream,
        monkeypatch: pytest.MonkeyPatch,
        error: Exception,
    ) -> None:
        """Connect failures and connect timeouts back off."""
        _arm(stream, monkeypatch, error)
        with pytest.raises(StreamError, match="network error opening") as ei:
            stream._connect_once()
        assert ei.value.__cause__ is error

    @pytest.mark.parametrize(
        ("status", "kind"),
        [(401, "rejected"), (403, "rejected"), (500, "failed")],
    )
    def test_http_errors_are_classified(
        self,
        stream: SessionStream,
        monkeypatch: pytest.MonkeyPatch,
        status: int,
        kind: str,
    ) -> None:
        """401/403 name the token or rules; others are plain failures."""
        response = fake_response(status_code=status, text="denied")
        _arm(stream, monkeypatch, response)
        with pytest.raises(StreamError, match=f"stream {kind}.*HTTP {status} denied"):
            stream._connect_once()


class TestRunOne:
    """One connection, its outcome and what gets logged."""

    def test_clean_end_is_planned(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returning normally means renewal or auth_revoked: planned."""
        monkeypatch.setattr(stream, "_connect_once", lambda: None)
        assert stream._run_one() is True

    def test_stream_error_is_a_warning(
        self,
        stream: SessionStream,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A StreamError is unplanned and logged at WARNING with the fallback."""

        def boom() -> None:
            msg = "HTTP 500"
            raise StreamError(msg)

        monkeypatch.setattr(stream, "_connect_once", boom)
        with caplog.at_level(logging.WARNING):
            assert stream._run_one() is False
        (record,) = caplog.records
        assert record.levelno == logging.WARNING
        assert "HTTP 500" in record.getMessage()
        assert "15-min workout-sync" in record.getMessage()

    def test_unexpected_exception_is_logged_with_traceback(
        self,
        stream: SessionStream,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A bug must not kill the thread -- and must not be silent."""

        def boom() -> None:
            msg = "bug"
            raise RuntimeError(msg)

        monkeypatch.setattr(stream, "_connect_once", boom)
        with caplog.at_level(logging.WARNING):
            assert stream._run_one() is False
        (record,) = caplog.records
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert "crashed" in record.getMessage()
