"""Tests for _session_stream: byte metering, event dispatch and token renewal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record
import pytest
import requests
import urllib3

from screen_locker import _session_stream, _stream_cache
from screen_locker._poke_credit import BatchOutcome
from screen_locker._session_stream import SessionStream
from screen_locker._stream_auth import StreamError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_FUTURE = datetime(2999, 1, 1, tzinfo=UTC)
_PAST = datetime.now(UTC) - timedelta(hours=1)
_LEAF = "log~2Ejson"
KEEPALIVE = ("keep-alive", "null")


class FakeRaw:
    """``response.raw``: yields queued chunks, raises queued exceptions."""

    def __init__(self, chunks: Iterable[bytes | Exception]) -> None:
        self.chunks = list(chunks)
        self.closed = False

    def read1(self, _size: int) -> bytes:
        """The next chunk (``b""`` at EOF), or raise the queued error."""
        if not self.chunks:
            return b""
        item = self.chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        """Mark the connection released."""
        self.closed = True


def fake_response(
    chunks: Iterable[bytes | Exception] = (),
    status_code: int = 200,
    text: str = "",
) -> requests.Response:
    """A real ``Response`` whose body is the queued chunks (no sockets)."""
    response = requests.Response()
    response.status_code = status_code
    response.encoding = "utf-8"
    response._content = text.encode()
    response.raw = FakeRaw(chunks)
    return response


def sse(*events: tuple[str, str]) -> bytes:
    """Encode ``(name, data)`` pairs as an SSE byte stream."""
    return b"".join(f"event: {n}\ndata: {d}\n\n".encode() for n, d in events)


def make_stream(monkeypatch: pytest.MonkeyPatch) -> SessionStream:
    """A stream with a fake device identity (the real one mints a file)."""
    identity = SimpleNamespace(device_id="pc-new", legacy_id="pc-old")
    monkeypatch.setattr(_session_stream, "device_identity", lambda: identity)
    return SessionStream(threading.Lock())


@pytest.fixture
def stream(monkeypatch: pytest.MonkeyPatch) -> SessionStream:
    """A ``SessionStream`` that never reads or writes the real device id."""
    return make_stream(monkeypatch)


def _put(data: object, path: str = "/") -> tuple[str, str]:
    return "put", json.dumps({"path": path, "data": data})


class TestConsume:
    """Dispatching events until the server or the renew deadline ends it."""

    def test_snapshot_and_patch_are_credited(
        self, stream: SessionStream, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Real cache + fake credit: snapshot then patch each credit once."""
        batches: list[list[str]] = []

        def credit(records: Iterable[tuple[str, Mapping[str, object]]]) -> BatchOutcome:
            ids = [rid for rid, _p in records]
            batches.append(ids)
            return BatchOutcome(tuple(ids), len(ids))

        monkeypatch.setattr(_stream_cache._poke_credit, "credit_sessions", credit)
        log = _session_log("s1")
        log2 = _session_log("s2")
        body = sse(
            _put({"phone": {_LEAF: log}}),
            ("patch", json.dumps({"path": "/", "data": {f"phone/{_LEAF}": log2}})),
            ("auth_revoked", '"expired"'),
        )
        stream._consume(fake_response([body]), _FUTURE)
        assert batches == [["s1"], ["s2"]]
        assert stream._got_snapshot is True

    def test_keepalives_are_logged_only_a_few_times(
        self,
        stream: SessionStream,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Keep-alive events 1..3 are logged; later ones are silent."""
        body = sse(*[("keep-alive", "null")] * 5, ("auth_revoked", "x"))
        with caplog.at_level(logging.INFO):
            stream._consume(fake_response([body]), _FUTURE)
        seen = [
            r.getMessage() for r in caplog.records if "keep-alive #" in r.getMessage()
        ]
        assert seen == [f"Session stream keep-alive #{n}" for n in (1, 2, 3)]

    def test_auth_revoked_returns_with_a_warning(
        self, stream: SessionStream, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A revoked token ends the connection on purpose, loudly."""
        with caplog.at_level(logging.WARNING):
            stream._consume(
                fake_response([sse(("auth_revoked", "stale"))]),
                _FUTURE,
            )
        assert any(
            "token revoked/expired (stale)" in r.getMessage()
            and r.levelno == logging.WARNING
            for r in caplog.records
        )

    def test_cancel_is_a_stream_error(self, stream: SessionStream) -> None:
        """``cancel`` means the rules deny us: back off."""
        response = fake_response([sse(("cancel", "permission_denied"))])
        with pytest.raises(
            StreamError, match=r"cancelled the stream \(permission_denied\)"
        ):
            stream._consume(response, _FUTURE)

    def test_unknown_event_is_warned_about_and_ignored(
        self, stream: SessionStream, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unexpected events are logged at WARNING and the stream carries on."""
        response = fake_response([sse(("mystery", "?"), ("auth_revoked", "x"))])
        with caplog.at_level(logging.WARNING):
            stream._consume(response, _FUTURE)
        assert any("ignored event 'mystery'" in r.getMessage() for r in caplog.records)

    def test_token_is_renewed_before_expiry(
        self, stream: SessionStream, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Once the renew deadline passes, the next event ends it cleanly."""
        response = fake_response([sse(("keep-alive", "null"), ("keep-alive", "null"))])
        with caplog.at_level(logging.INFO):
            stream._consume(response, _PAST)
        assert any("renewing its ID token" in r.getMessage() for r in caplog.records)
        assert response.raw.chunks == []
        keepalives = [r for r in caplog.records if "keep-alive #" in r.getMessage()]
        assert len(keepalives) == 1  # stopped after the first event

    def test_server_closing_unasked_is_a_stream_error(
        self, stream: SessionStream
    ) -> None:
        """EOF without auth_revoked/renewal is a failure, with a byte count."""
        response = fake_response([sse(("keep-alive", "null"))])
        with pytest.raises(
            StreamError,
            match=f"server closed the stream after {len(sse(KEEPALIVE))} bytes",
        ):
            stream._consume(response, _FUTURE)

    @pytest.mark.parametrize(
        "error",
        [
            requests.exceptions.ReadTimeout("read timed out"),
            requests.exceptions.ChunkedEncodingError("cut"),
            urllib3.exceptions.ProtocolError("connection broken"),
            TimeoutError("socket timeout"),
        ],
    )
    def test_read_errors_and_timeouts_become_stream_errors(
        self, stream: SessionStream, error: Exception
    ) -> None:
        """A silent socket (read timeout) or broken read ends in StreamError."""
        response = fake_response([sse(("keep-alive", "null")), error])
        with pytest.raises(
            StreamError, match=f"stream broke after {len(sse(KEEPALIVE))} bytes"
        ) as ei:
            stream._consume(response, _FUTURE)
        assert ei.value.__cause__ is error


def _session_log(rid: str) -> str:
    """A device-log blob with one completed-session record."""
    record = Record(rid, {"payload": ({"exercises": []}, Hlc(1, 0, "n"))})
    return json.dumps({rid: record.to_dict()})
