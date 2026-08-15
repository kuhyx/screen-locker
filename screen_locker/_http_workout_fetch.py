"""HTTP fallback for phone verification: find the app's server, fetch JSON.

Split out of :mod:`screen_locker._phone_verification` to keep every file under
the 250-line cap. Composed back into ``PhoneVerificationMixin`` there, so
callers see no change.

Used when adb cannot reach the phone but it is on the same wifi: the workout
app serves the same JSON over ``WORKOUT_HTTP_PORT``.
"""

from __future__ import annotations

from concurrent.futures import (  # pylint: disable=no-name-in-module
    ThreadPoolExecutor,
    as_completed,
)
import contextlib
from http import client as _http_client
import json
import logging
import socket

from screen_locker._constants import WORKOUT_HTTP_PORT

_HTTPConnection = _http_client.HTTPConnection
_HTTPException = _http_client.HTTPException
_HTTP_OK = _http_client.OK

_logger = logging.getLogger(__name__)


class HttpWorkoutFetchMixin:
    """Scans the local subnet for the workout app's HTTP server."""

    def _scan_for_http_server(self) -> str | None:
        """Scan local /24 subnet for the workout app HTTP server on port 8765.

        Returns the first reachable URL or None.
        """
        prefix = self._get_local_subnet_prefix()
        if prefix is None:
            return None

        def probe(i: int) -> str | None:
            ip = f"{prefix}.{i}"
            with (
                contextlib.suppress(OSError),
                socket.create_connection((ip, WORKOUT_HTTP_PORT), timeout=0.3),
            ):
                return f"http://{ip}:{WORKOUT_HTTP_PORT}/workout"
            return None

        _logger.info(
            "Scanning %s.1-254:%d for workout app...", prefix, WORKOUT_HTTP_PORT
        )
        with ThreadPoolExecutor(max_workers=64) as executor:
            for future in as_completed(
                executor.submit(probe, i) for i in range(1, 255)
            ):
                result = future.result()
                if result is not None:
                    return result
        return None

    def _fetch_http_workout(self) -> dict | None:
        """Fetch workout JSON from the app's HTTP server on the local network.

        Uses http.client directly to avoid urllib URL-open security lint rules.
        The URL is always http://<local-ip>:8765/workout — no user input involved.
        """
        url = self._scan_for_http_server()
        if url is None:
            return None
        # url is always "http://<ip>:<port>/workout" — constructed internally.
        try:
            _, _, hostport = url.partition("://")
            host, _, path = hostport.partition("/")
            hostname, _, port_str = host.partition(":")
            conn = _HTTPConnection(hostname, int(port_str), timeout=5)
            conn.request("GET", f"/{path}")
            resp = conn.getresponse()
            if resp.status != _HTTP_OK:
                return None
            return json.loads(resp.read().decode())
        except (_HTTPException, OSError, ValueError, json.JSONDecodeError) as exc:
            _logger.warning(
                "HTTP fetch of today's workout from %s failed (%s) — no data "
                "from the phone's HTTP server, so verification falls through",
                url,
                exc,
            )
            return None

    # ── Main verification entry point ─────────────────────────────────────────
