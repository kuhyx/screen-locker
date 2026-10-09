"""The poke HTTP front end, driven over real loopback HTTP on an ephemeral port."""

from __future__ import annotations

import hashlib
import hmac
from http.client import HTTPConnection
import json
import socket
import threading
import time
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from screen_locker import _poke_credit, _poke_server
from screen_locker._poke_server import MAX_BODY_BYTES, POKE_PATH, PokeServer

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# conftest stubs socket.create_connection process-wide (see test_web_server).
_REAL_CREATE_CONNECTION = socket.create_connection
_KEY = bytes(range(32))


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _body(nonce: str = "n-1", **overrides: object) -> bytes:
    doc: dict[str, Any] = {
        "v": 1,
        "sent_at_ms": _now_ms(),
        "nonce": nonce,
        "sandbox": False,
        "record_id": "rec-1",
        "payload": {"date": "2026-10-09", "note": "zażółć"},
    }
    doc.update(overrides)
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


def _sign(body: bytes) -> str:
    return hmac.new(_KEY, body, hashlib.sha256).hexdigest()


@pytest.fixture
def port(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """A running PokeServer on 127.0.0.1:0; shut down afterwards."""
    monkeypatch.setattr(socket, "create_connection", _REAL_CREATE_CONNECTION)
    server = PokeServer(("127.0.0.1", 0), _KEY)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def credit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
    """Stub the PC side: tmp locker, fixed snapshot, a spy for the credit."""
    locker = MagicMock()
    locker.log_file = tmp_path / "log.json"
    monkeypatch.setattr(_poke_credit, "fresh_locker", lambda: locker)
    monkeypatch.setattr(_poke_credit, "current_shutdown", lambda: "20:30")
    monkeypatch.setattr(_poke_credit, "current_gaming_minutes", lambda _p: 75)
    spy = MagicMock(
        return_value=_poke_credit.PokeOutcome(
            ok=True, credited=True, duplicate=False, reason="workout credited"
        )
    )
    monkeypatch.setattr(_poke_credit, "credit_session", spy)
    return spy


def _post(
    port: int,
    body: bytes,
    signature: str | None,
    path: str = POKE_PATH,
) -> tuple[int, dict[str, Any]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Poke-Signature"] = signature
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return resp.status, data


def _raw(port: int, lines: list[str], send: bytes = b"") -> tuple[int, dict[str, Any]]:
    """A hand-written POST (so headers http.client would add can be omitted)."""
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", POKE_PATH)
    for line in lines:
        name, value = line.split(": ", 1)
        conn.putheader(name, value)
    conn.endheaders()
    if send and conn.sock is not None:
        conn.sock.sendall(send)
    if conn.sock is not None:
        conn.sock.shutdown(socket.SHUT_WR)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return resp.status, data


class TestCredit:
    def test_valid_poke_credits_and_answers_the_contract_shape(
        self, port: int, credit: MagicMock
    ) -> None:
        body = _body()
        status, reply = _post(port, body, _sign(body))
        assert status == 200
        assert reply["ok"] is True
        assert reply["credited"] is True
        assert reply["duplicate"] is False
        assert reply["sandbox"] is False
        assert reply["shutdown"] == "20:30"
        assert reply["gaming_budget_minutes"] == 75
        assert isinstance(reply["pc_ms"], int)
        credit.assert_called_once_with(
            "rec-1", {"date": "2026-10-09", "note": "zażółć"}
        )

    def test_replayed_nonce_is_409_and_credits_once(
        self, port: int, credit: MagicMock
    ) -> None:
        body = _body()
        assert _post(port, body, _sign(body))[0] == 200
        status, reply = _post(port, body, _sign(body))
        assert status == 409
        assert reply["ok"] is False
        assert reply["shutdown"] is None
        assert credit.call_count == 1

    def test_stale_timestamp_is_401(self, port: int, credit: MagicMock) -> None:
        body = _body(sent_at_ms=_now_ms() - 600_000)
        status, reply = _post(port, body, _sign(body))
        assert status == 401
        assert "stale" in reply["reason"]
        credit.assert_not_called()

    def test_bad_or_missing_signature_is_401(
        self, port: int, credit: MagicMock
    ) -> None:
        body = _body()
        assert _post(port, body, "00" * 32)[0] == 401
        assert _post(port, body, None)[0] == 401
        credit.assert_not_called()

    def test_schema_violation_is_400(self, port: int, credit: MagicMock) -> None:
        body = _body(v=2)
        status, reply = _post(port, body, _sign(body))
        assert status == 400
        assert "protocol version" in reply["reason"]
        credit.assert_not_called()

    def test_internal_error_is_500_and_says_the_sync_will_cover_it(
        self,
        port: int,
        credit: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        credit.side_effect = RuntimeError("boom")
        body = _body()
        status, reply = _post(port, body, _sign(body))
        assert status == 500
        assert reply["ok"] is False
        assert "regular sync will still credit" in reply["reason"]
        assert "crashed" in caplog.text


class TestSandbox:
    def test_sandbox_poke_over_http_is_answered_but_not_credited(
        self, port: int, credit: MagicMock
    ) -> None:
        body = _body(sandbox=True)
        status, reply = _post(port, body, _sign(body))
        assert (status, reply["ok"], reply["sandbox"]) == (200, True, True)
        assert reply["credited"] is False
        credit.assert_not_called()

    def test_sandbox_with_a_bad_signature_is_still_refused(
        self, port: int, credit: MagicMock
    ) -> None:
        status, reply = _post(port, _body(sandbox=True), "00" * 32)
        assert status == 401
        assert reply["sandbox"] is False


class TestRouting:
    def test_unknown_path_is_404(self, port: int, credit: MagicMock) -> None:
        body = _body()
        status, reply = _post(port, body, _sign(body), path="/v2/other")
        assert status == 404
        assert "unknown path" in reply["reason"]

    def test_get_is_405(self, port: int) -> None:
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", POKE_PATH)
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        assert resp.status == 405
        assert "only POST" in data["reason"]

    def test_missing_content_length_is_411(self, port: int) -> None:
        status, _ = _raw(port, ["Host: x"])
        assert status == 411

    @pytest.mark.parametrize("value", ["abc", "-5", ""])
    def test_malformed_content_length_is_400(self, port: int, value: str) -> None:
        status, reply = _raw(port, [f"Content-Length: {value}"])
        assert status == 400
        assert "bad Content-Length" in reply["reason"]

    def test_oversized_body_is_413_without_reading_it(self, port: int) -> None:
        status, reply = _raw(port, [f"Content-Length: {MAX_BODY_BYTES + 1}"])
        assert status == 413
        assert str(MAX_BODY_BYTES) in reply["reason"]

    def test_body_at_the_cap_is_read_and_judged_on_its_signature(
        self, port: int
    ) -> None:
        body = b"x" * MAX_BODY_BYTES
        assert _post(port, body, _sign(body))[0] == 400

    def test_truncated_body_is_400(self, port: int) -> None:
        status, reply = _raw(port, ["Content-Length: 100"], send=b"0123456789")
        assert status == 400
        assert "10 of 100 bytes" in reply["reason"]


def test_reply_for_a_refusal_leaves_the_snapshot_null() -> None:
    reply = _poke_server._refused("nope")
    assert reply["ok"] is False
    assert (reply["shutdown"], reply["gaming_budget_minutes"]) == (None, None)
    assert reply["reason"] == "nope"
