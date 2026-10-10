"""The resident LAN listener that credits a phone workout within a second.

``workout-poke.service`` runs ``python3 -m screen_locker.poke_server``: a
stdlib ``ThreadingHTTPServer`` on ``0.0.0.0:8774`` (the firewall admits only
192.168.1.0/24) answering ``POST /v1/workout`` per
``docs/DOCS-workout-poke-contract.md``. Every import -- the locker, the
earned-time registry, gatelock -- is paid once at startup, so a request costs
only the credit itself.

The wire checks are pure (:mod:`screen_locker._poke_wire`); the crediting is
the sync's own ingest (:mod:`screen_locker._poke_credit`). One lock serialises
the nonce cache and every credit in this process; cross-process safety comes
from the locks the ingest and credit already hold.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import threading
import time
from typing import TYPE_CHECKING, Final

from screen_locker import _poke_credit
from screen_locker._poke_wire import (
    NonceCache,
    Rejection,
    check_request,
)

if TYPE_CHECKING:
    from screen_locker._poke_wire import PokeRequest

__all__ = ["MAX_BODY_BYTES", "POKE_PATH", "PokeServer"]

_logger: Final = logging.getLogger(__name__)

MAX_BODY_BYTES: Final = 64 * 1024
POKE_PATH: Final = "/v1/workout"
_HANDLER_TIMEOUT_S: Final = 10


def _reply(
    outcome: _poke_credit.PokeOutcome,
    *,
    sandbox: bool = False,
    snapshot: tuple[str | None, int | None] = (None, None),
) -> dict[str, object]:
    """The contract's response shape; ``pc_ms`` is filled in by the handler.

    ``snapshot`` is (tonight's shutdown ``HH:MM``, gaming minutes); refusals
    leave it null rather than tell an unverified caller anything.
    """
    shutdown, gaming = snapshot
    return {
        "ok": outcome.ok,
        "credited": outcome.credited,
        "duplicate": outcome.duplicate,
        "sandbox": sandbox,
        "shutdown": shutdown,
        "gaming_budget_minutes": gaming,
        "pc_ms": 0,
        "reason": outcome.reason,
    }


def _refused(reason: str) -> dict[str, object]:
    """A refusal's reply: not ok, nothing credited."""
    return _reply(
        _poke_credit.PokeOutcome(
            ok=False, credited=False, duplicate=False, reason=reason
        )
    )


def _process(request: PokeRequest) -> dict[str, object]:
    """Credit (or, for a sandbox request, only answer) one verified poke."""
    locker = _poke_credit.fresh_locker()
    if request.sandbox:
        outcome = _poke_credit.PokeOutcome(
            ok=True,
            credited=False,
            duplicate=False,
            reason="sandbox request verified; nothing written or credited",
        )
    else:
        outcome = _poke_credit.credit_session(request.record_id, request.payload)
    return _reply(
        outcome,
        sandbox=request.sandbox,
        snapshot=(
            _poke_credit.current_shutdown(),
            _poke_credit.current_gaming_minutes(locker.log_file),
        ),
    )


class PokeServer(ThreadingHTTPServer):
    """Holds the key, the nonce cache and the one credit lock."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], key: bytes) -> None:
        """Bind ``address`` and serve :class:`PokeHandler` with ``key``."""
        super().__init__(address, PokeHandler)
        self.key = key
        self.nonces = NonceCache()
        self.gate = threading.Lock()


class PokeHandler(BaseHTTPRequestHandler):
    """``POST /v1/workout``; anything else is answered 404/405 in JSON."""

    server: PokeServer
    timeout = _HANDLER_TIMEOUT_S
    server_version = "workout-poke/1"

    # The default access log (one stderr line per request) is kept: the
    # journal is where it lands, and every refusal is also logged at warning.

    def do_GET(self) -> None:
        """Only POST exists."""
        self._send(
            *self._refusal(
                Rejection(
                    HTTPStatus.METHOD_NOT_ALLOWED, f"only POST {POKE_PATH} exists"
                )
            )
        )

    def do_POST(self) -> None:
        """Verify, credit and answer one poke; never let an error go unanswered."""
        started = time.perf_counter()
        try:
            status, reply = self._handle()
        except Exception:
            _logger.exception("Workout poke from %s crashed", self.client_address[0])
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            reply = _refused(
                "the PC hit an internal error (see its journal); the "
                "regular sync will still credit this session"
            )
        reply["pc_ms"] = round((time.perf_counter() - started) * 1000)
        self._send(status, reply)

    def _refusal(self, rejection: Rejection) -> tuple[HTTPStatus, dict[str, object]]:
        """Log a refusal at warning; the reply carries the same reason."""
        _logger.warning(
            "Workout poke from %s rejected (%d): %s",
            self.client_address[0],
            rejection.status,
            rejection.reason,
        )
        return rejection.status, _refused(rejection.reason)

    def _read_body(self) -> bytes | Rejection:
        """Exactly Content-Length bytes of ``POST /v1/workout``, capped.

        Over :data:`MAX_BODY_BYTES` is refused before reading a byte of it.
        """
        if self.path != POKE_PATH:
            return Rejection(
                HTTPStatus.NOT_FOUND, f"unknown path {self.path!r}; use {POKE_PATH}"
            )
        raw = self.headers.get("Content-Length")
        if raw is None:
            return Rejection(HTTPStatus.LENGTH_REQUIRED, "Content-Length is required")
        length = int(raw) if raw.strip().isdigit() else -1
        if length < 0:
            return Rejection(HTTPStatus.BAD_REQUEST, f"bad Content-Length {raw!r}")
        if length > MAX_BODY_BYTES:
            return Rejection(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"body is {length} bytes; the limit is {MAX_BODY_BYTES}",
            )
        body = self.rfile.read(length)
        if len(body) != length:
            return Rejection(
                HTTPStatus.BAD_REQUEST,
                f"body ended after {len(body)} of {length} bytes",
            )
        return body

    def _handle(self) -> tuple[HTTPStatus, dict[str, object]]:
        """Run the contract's checks, then credit; returns (status, reply)."""
        body = self._read_body()
        if isinstance(body, Rejection):
            return self._refusal(body)
        with self.server.gate:
            verdict = check_request(
                self.server.key,
                body,
                self.headers.get("X-Poke-Signature"),
                self.server.nonces,
                now_ms=time.time_ns() // 1_000_000,
            )
            if isinstance(verdict, Rejection):
                return self._refusal(verdict)
            reply = _process(verdict)
        _logger.info(
            "Workout poke %s (sandbox=%s): %s",
            verdict.record_id,
            verdict.sandbox,
            reply["reason"],
        )
        return HTTPStatus.OK, reply

    def _send(self, status: HTTPStatus, reply: dict[str, object]) -> None:
        """Write ``reply`` as a JSON response and close the connection."""
        data = json.dumps(reply, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
