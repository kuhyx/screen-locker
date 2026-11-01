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

from screen_locker import _poke_credit
from screen_locker._poke_server import POKE_PATH, PokeServer

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# conftest stubs socket.create_connection process-wide (see test_web_server).
_real_create_connection = socket.create_connection
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


@pytest.fixture(name="port")
def port_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """A running PokeServer on 127.0.0.1:0; shut down afterwards."""
    monkeypatch.setattr(socket, "create_connection", _real_create_connection)
    server = PokeServer(("127.0.0.1", 0), _KEY)
    # poll_interval: shutdown() waits out one poll, 0.5 s per test by default.
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(name="credit")
def credit_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
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
    """A signed poke over real HTTP and the status each failure mode maps to."""

    def test_valid_poke_credits_and_answers_the_contract_shape(
        self, port: int, credit: MagicMock
    ) -> None:
        """A valid poke credits once and the reply carries the full contract shape."""
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
        """Replaying a nonce is refused with 409 and never credits twice."""
        body = _body()
        assert _post(port, body, _sign(body))[0] == 200
        status, reply = _post(port, body, _sign(body))
        assert status == 409
        assert reply["ok"] is False
        assert reply["shutdown"] is None
        assert credit.call_count == 1

    def test_stale_timestamp_is_401(self, port: int, credit: MagicMock) -> None:
        """A poke with an old timestamp is rejected as stale and not credited."""
        body = _body(sent_at_ms=_now_ms() - 600_000)
        status, reply = _post(port, body, _sign(body))
        assert status == 401
        assert "stale" in reply["reason"]
        credit.assert_not_called()

    def test_bad_or_missing_signature_is_401(
        self, port: int, credit: MagicMock
    ) -> None:
        """A wrong or absent signature is rejected with 401 and not credited."""
        body = _body()
        assert _post(port, body, "00" * 32)[0] == 401
        assert _post(port, body, None)[0] == 401
        credit.assert_not_called()

    def test_schema_violation_is_400(self, port: int, credit: MagicMock) -> None:
        """An unsupported protocol version is a 400 and not credited."""
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
        """A crash in crediting gives a 500 that says the regular sync will still credit."""
        credit.side_effect = RuntimeError("boom")
        body = _body()
        status, reply = _post(port, body, _sign(body))
        assert status == 500
        assert reply["ok"] is False
        assert "regular sync will still credit" in reply["reason"]
        assert "crashed" in caplog.text


class TestSandbox:
    """Sandbox pokes are acknowledged but never credited, and still need a valid signature."""

    def test_sandbox_poke_over_http_is_answered_but_not_credited(
        self, port: int, credit: MagicMock
    ) -> None:
        """A signed sandbox poke is answered ok without crediting anything."""
        body = _body(sandbox=True)
        status, reply = _post(port, body, _sign(body))
        assert (status, reply["ok"], reply["sandbox"]) == (200, True, True)
        assert reply["credited"] is False
        credit.assert_not_called()

    def test_sandbox_with_a_bad_signature_is_still_refused(
        self, port: int, credit: MagicMock
    ) -> None:
        """A sandbox poke with a bad signature is refused and not flagged as sandbox."""
        status, reply = _post(port, _body(sandbox=True), "00" * 32)
        assert status == 401
        assert reply["sandbox"] is False
