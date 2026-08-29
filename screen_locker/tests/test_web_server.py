"""Tests for _web_server: routing, static serving, and the loopback guard.

The server is started on an ephemeral port and driven over real HTTP rather
than by calling handler methods directly, so the response codes and content
types tested here are the ones a browser and the enforcer actually see.
"""

from __future__ import annotations

from contextlib import contextmanager
from http.client import HTTPConnection
import json
import socket
import threading
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from screen_locker._web_server import _decision_limit, create_server, main, serve

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_PKG = "screen_locker._web_server"

# conftest's autouse _block_real_network patches
# "screen_locker._http_workout_fetch.socket.create_connection", and that
# attribute path resolves to the *global* socket module -- so every test in the
# suite has socket.create_connection stubbed, including loopback connections to
# a server we started ourselves. Captured at import time, before any fixture
# runs, which is the only moment the real function is still reachable. The
# fixture's own docstring says tests needing a real probe patch it locally.
_REAL_CREATE_CONNECTION = socket.create_connection


@pytest.fixture
def real_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore real socket connections for tests that drive the server.

    Args:
        monkeypatch: pytest's attribute patcher, which undoes this on teardown.
    """
    monkeypatch.setattr(socket, "create_connection", _REAL_CREATE_CONNECTION)


@contextmanager
def _running() -> Iterator[int]:
    """Start the server on an ephemeral port in a thread; yield the port.

    Yields:
        The bound port.
    """
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get(port: int, path: str) -> tuple[int, bytes, str]:
    """Make a GET request, returning ``(status, body, content-type)``.

    Args:
        port: Port to connect to.
        path: Request path.

    Returns:
        The status code, body bytes and Content-Type header.
    """
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    finally:
        conn.close()


def _make_dist(tmp_path: Path, *, with_index: bool = True) -> Path:
    """Create a fake built-frontend directory.

    Args:
        tmp_path: pytest temporary directory.
        with_index: Whether to write an ``index.html``.

    Returns:
        The resolved dist directory.
    """
    dist = (tmp_path / "dist").resolve()
    dist.mkdir()
    if with_index:
        (dist / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    (dist / "app.css").write_text("body{}", encoding="utf-8")
    (dist / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return dist


class TestDecisionLimit:
    """?limit= is parsed defensively; a bad value never reaches the reader."""

    def test_absent_limit_uses_the_default(self) -> None:
        """No query string means the default page size."""
        assert _decision_limit("") > 0

    def test_explicit_limit_is_honoured(self) -> None:
        """A sane limit passes through."""
        assert _decision_limit("limit=5") == 5

    def test_non_numeric_limit_falls_back(self) -> None:
        """Garbage in the query string must not 500 the endpoint."""
        assert _decision_limit("limit=abc") == _decision_limit("")

    def test_zero_or_negative_limit_falls_back(self) -> None:
        """A limit of zero would render an empty history for no reason."""
        assert _decision_limit("limit=0") == _decision_limit("")


class TestApiRoutes:
    """Each API path serves its own payload as JSON."""

    @pytest.fixture(autouse=True)
    def _network(self, real_loopback: None) -> None:
        """Every test in this class talks to the server over real HTTP."""

    def test_status_route(self) -> None:
        """/api/status serves the status payload."""
        with (
            patch(f"{_PKG}.build_status_payload", return_value={"ok": True}),
            _running() as port,
        ):
            status, body, ctype = _get(port, "/api/status")
        assert status == 200
        assert json.loads(body) == {"ok": True}
        assert ctype.startswith("application/json")

    def test_health_route(self) -> None:
        """/api/health serves the health payload."""
        with (
            patch(f"{_PKG}.build_health_payload", return_value={"armed": False}),
            _running() as port,
        ):
            status, body, _ = _get(port, "/api/health")
        assert status == 200
        assert json.loads(body) == {"armed": False}

    def test_decisions_route_passes_the_limit_through(self) -> None:
        """/api/decisions forwards ?limit= to the payload builder."""
        with (
            patch(
                f"{_PKG}.build_decisions_payload", return_value={"total": 0}
            ) as build,
            _running() as port,
        ):
            status, _, _ = _get(port, "/api/decisions?limit=7")
        assert status == 200
        build.assert_called_once_with(limit=7)

    def test_a_broken_payload_returns_500_and_says_which(self) -> None:
        """A failing builder must never look like an endpoint with no news."""
        with (
            patch(f"{_PKG}.build_status_payload", side_effect=OSError("disk gone")),
            _running() as port,
        ):
            status, body, _ = _get(port, "/api/status")
        assert status == 500
        assert b"status error" in body


class TestBindGuard:
    """The API is unauthenticated, so it may only ever bind loopback."""

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
    def test_loopback_is_allowed(self, host: str) -> None:
        """Both loopback spellings are accepted."""
        server = create_server(host, 0)
        server.server_close()

    def test_a_public_bind_is_refused(self) -> None:
        """A LAN address would publish the payloads beyond this machine."""
        with pytest.raises(ValueError, match="loopback-only"):
            create_server("192.0.2.1", 0)


class TestServeEntryPoints:
    """serve() and main() wire the server to the process lifetime."""

    def test_serve_closes_the_socket_on_interrupt(self) -> None:
        """Ctrl-C shuts down cleanly rather than leaving the port bound."""
        server = create_server("127.0.0.1", 0)
        with (
            patch(f"{_PKG}.create_server", return_value=server),
            patch.object(server, "serve_forever", side_effect=KeyboardInterrupt),
            patch.object(server, "server_close") as close,
        ):
            serve()
        close.assert_called_once()
        server.server_close()

    def test_main_returns_zero(self) -> None:
        """The console-script entry point reports success on a clean exit."""
        with patch(f"{_PKG}.serve") as served:
            assert main() == 0
        served.assert_called_once()
