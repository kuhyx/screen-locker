"""Read-only localhost HTTP server for the status web UI.

Serves the status/decision/health payloads at ``/api/*`` and the built React
bundle (``web/dist``) as static files. Binds to loopback only and never exposes
a secret: every payload comes from :mod:`screen_locker._web_payload`, which
reads state files but never the sync token or the HMAC key.

Read-only by construction, like the MCP server it sits beside: there is no
route that logs a workout, clears a lock, or writes anything at all. A local
web page that could log a workout would be a hole straight through the gate.

Two things depend on this process being up: the browser UI, and
steam-backlog-enforcer, which asks ``/api/status`` whether today has a workout
before deciding the gaming budget. The enforcer fails closed to the smaller
budget when this is unreachable, so a dead server costs gaming time rather than
silently handing it back.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from screen_locker._web_decisions import (
    DEFAULT_DECISION_LIMIT,
    build_decisions_payload,
)
from screen_locker._web_payload import (
    build_health_payload,
    build_status_payload,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Built frontend lives at <repo>/web/dist (sibling of the package directory).
WEB_DIST = (Path(__file__).resolve().parent.parent / "web" / "dist").resolve()

DEFAULT_HOST = "127.0.0.1"
# 8000 is taken by steam-backlog-enforcer's own web UI.
DEFAULT_PORT = 8770

_API_STATUS = "/api/status"
_API_DECISIONS = "/api/decisions"
_API_HEALTH = "/api/health"

# Content types that are text but not under the ``text/`` prefix.
_EXTRA_TEXT_TYPES = frozenset(
    {"application/javascript", "application/json", "image/svg+xml"}
)
_NOT_BUILT_MSG = (
    b"Frontend not built. Run: npm --prefix web install && npm --prefix web run build"
)


def _decision_limit(query: str) -> int:
    """Parse ``?limit=`` from a query string, falling back to the default.

    Args:
        query: The raw query string.

    Returns:
        A positive limit; the default when absent, non-numeric or out of range.
    """
    raw = parse_qs(query).get("limit", [""])[0]
    try:
        value = int(raw)
    except ValueError:
        if raw:
            # Benign (a hand-typed URL), but say so: a silently ignored
            # parameter is how someone concludes the endpoint is broken.
            logger.warning(
                "Ignoring unparsable ?limit=%r; serving the default %d decisions",
                raw,
                DEFAULT_DECISION_LIMIT,
            )
        return DEFAULT_DECISION_LIMIT
    return value if value > 0 else DEFAULT_DECISION_LIMIT


class _Handler(BaseHTTPRequestHandler):
    """Serve the status payloads and the static frontend bundle (read-only)."""

    def log_message(self, fmt: str, *args: object) -> None:
        """Route the default request log to ``logging`` at debug level.

        Args:
            fmt: printf-style format string from BaseHTTPRequestHandler.
            args: Its arguments.
        """
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        """Dispatch a GET to one of the APIs or to a static file."""
        split = urlsplit(self.path)
        if split.path == _API_STATUS:
            self._serve_json("status", build_status_payload)
        elif split.path == _API_DECISIONS:
            limit = _decision_limit(split.query)
            self._serve_json("decisions", lambda: build_decisions_payload(limit=limit))
        elif split.path == _API_HEALTH:
            self._serve_json("health", build_health_payload)
        else:
            self._serve_static(split.path)

    def _serve_json(self, name: str, build: Callable[[], dict[str, Any]]) -> None:
        """Build a payload and send it as JSON, or a 500 naming the failure.

        Args:
            name: Payload name, used in the error message and the log.
            build: Zero-argument callable returning the payload.
        """
        try:
            body = json.dumps(build()).encode("utf-8")
        except OSError, ValueError, KeyError, TypeError:
            # Never a bare swallow: the reason has to reach the journal, or a
            # broken endpoint looks identical to an endpoint with nothing to say.
            logger.exception("Failed to build the %s payload", name)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"{name} error - see the journal for screen-locker-web".encode(),
                "text/plain",
            )
            return
        self._send(HTTPStatus.OK, body, "application/json")

    def _serve_static(self, path: str) -> None:
        """Serve a file from ``WEB_DIST`` with SPA fallback and traversal guard.

        Args:
            path: The request path.
        """
        rel = path.lstrip("/") or "index.html"
        candidate = (WEB_DIST / rel).resolve()
        # Reject path traversal, then fall back to index.html for SPA routes.
        if not candidate.is_relative_to(WEB_DIST) or not candidate.is_file():
            candidate = WEB_DIST / "index.html"
        if not candidate.is_file():
            self._send(HTTPStatus.NOT_FOUND, _NOT_BUILT_MSG, "text/plain")
            return
        ctype, _ = mimetypes.guess_type(candidate.name)
        self._send(HTTPStatus.OK, candidate.read_bytes(), ctype or "text/plain")

    def _send(self, status: HTTPStatus, body: bytes, ctype: str) -> None:
        """Write a complete response with the given status, body, and type.

        Args:
            status: HTTP status to send.
            body: Response body.
            ctype: Content type, charset appended for text types.
        """
        if ctype.startswith("text/") or ctype in _EXTRA_TEXT_TYPES:
            ctype = f"{ctype}; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    """Create (but do not start) the threading HTTP server.

    Args:
        host: Address to bind. Must stay on loopback: the API is unauthenticated.
        port: Port to bind.

    Returns:
        The unstarted server.

    Raises:
        ValueError: If asked to bind anywhere but loopback.
    """
    if not host.startswith("127.") and host != "localhost":
        # The payloads are unauthenticated, so a bind must never leave this
        # machine. Refuse loudly rather than quietly publishing them.
        msg = f"Refusing to bind {host}: the status API is loopback-only"
        raise ValueError(msg)
    return ThreadingHTTPServer((host, port), _Handler)


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Run the web server until interrupted.

    Args:
        host: Address to bind.
        port: Port to bind.
    """
    server = create_server(host, port)
    logger.info("Screen locker status UI: http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # Warning, not info: this process is load-bearing for the gaming
        # budget, so its shutdown must be visible in the journal.
        logger.warning("Interrupted — shutting the status server down.")
    finally:
        server.server_close()


def main() -> int:
    """Console-script entry point for ``screen-locker-web``.

    Returns:
        Process exit code.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
