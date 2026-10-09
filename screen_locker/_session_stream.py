"""Off-LAN instant credit: hold a Firebase RTDB stream of the device logs.

Off the home LAN the phone's only transport is Firebase, so without this a
finished session waits up to 15 minutes for ``workout-sync.timer``. This
thread, inside ``workout-poke.service``, keeps ``GET
<db>/screen-locker-sync/devices.json`` open as Server-Sent Events and credits
each newly streamed session within about a second
(:class:`screen_locker._stream_cache.DeviceLogCache`).

Free-tier budget (Spark: 10 GB/month download, no per-read quota). Every
(re)connect downloads the whole devices node once: 375,755 bytes measured on
2026-10-09 (18 device dirs; logged with each snapshot, after transfer
decoding, so an upper bound on the wire). The ID token lives one hour, so
that is ~24 snapshots a day, ~9 MB: less than the 15-min sync, which fetches
every device log on every tick. After the snapshot, a write streams only the
written device's whole log: ~83 KB for the current phone, ~43 KB for each PC
push. RTDB sends NO event for a byte-identical write (observed), and the
phone's home-screen ``syncNow`` skips the write when its log is unchanged, so
no-op syncs cost nothing. Nothing here issues a read beyond the stream.

Every failure is logged at warning or above with what it means, the thread
backs off (1 s doubling to 60 s, jittered) and never touches the HTTP
listener. The sync stays the safety net: the stream only makes credit faster.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import random
import threading
import time
from typing import TYPE_CHECKING, Final

import requests
import urllib3

from screen_locker._device import device_identity
from screen_locker._rtdb_stream import parse_sse
from screen_locker._stream_auth import StreamError, stream_auth
from screen_locker._stream_cache import DeviceLogCache
from screen_locker._workout_sync import _DEVICES_PREFIX

if TYPE_CHECKING:
    from collections.abc import Iterator

    from screen_locker._rtdb_stream import SseEvent

__all__ = ["SessionStream"]

_logger: Final = logging.getLogger(__name__)

_FALLBACK: Final = (
    "off-LAN workouts will only be credited by the 15-min workout-sync until "
    "this recovers"
)
_BACKOFF_MIN_S: Final = 1.0
_BACKOFF_MAX_S: Final = 60.0
# RTDB sends a keep-alive every ~30 s; silence past this means a dead socket.
_TIMEOUT_S: Final = (10, 90)
_LOGGED_KEEPALIVES: Final = 3
_HTTP_AUTH_REJECTED: Final = (401, 403)
# A connection that ends sooner than this pays a backoff even when the end was
# planned (auth_revoked, renewal): no path may reconnect in a tight loop, and
# each reconnect re-downloads the snapshot.
_MIN_LIFETIME_S: Final = 300.0
_STREAM_ERRORS: Final = (
    requests.RequestException,
    urllib3.exceptions.HTTPError,
    OSError,
)
_JITTER: Final = random.SystemRandom()


class SessionStream:
    """A daemon thread holding the stream; one connection at a time."""

    def __init__(self, gate: threading.Lock) -> None:
        """``gate`` is the poke server's credit lock, so credits never race."""
        identity = device_identity()
        self._cache = DeviceLogCache(
            _DEVICES_PREFIX,
            frozenset({identity.device_id, identity.legacy_id}),
            gate,
        )
        self._http = requests.Session()
        self._stop = threading.Event()
        self._got_snapshot = False

    def start(self) -> threading.Thread:
        """Run :meth:`run_forever` on a daemon thread and return it."""
        thread = threading.Thread(
            target=self.run_forever, name="firebase-session-stream", daemon=True
        )
        thread.start()
        return thread

    def stop(self) -> None:
        """Ask the loop to exit after the current connection."""
        self._stop.set()

    def run_forever(self) -> None:
        """Connect, stream, back off on failure; never raise out of the thread."""
        delay = _BACKOFF_MIN_S
        while not self._stop.is_set():
            self._got_snapshot = False
            opened = time.monotonic()
            planned = self._run_one()
            lived = time.monotonic() - opened >= _MIN_LIFETIME_S
            if self._got_snapshot and lived:
                delay = _BACKOFF_MIN_S
            if planned and lived:
                continue  # a long-lived connection ending on schedule
            pause = delay * _JITTER.uniform(0.5, 1.0)
            delay = min(delay * 2, _BACKOFF_MAX_S)
            _logger.warning("Reconnecting the session stream in %.1f s", pause)
            self._stop.wait(pause)

    def _run_one(self) -> bool:
        """One connection; True if it ended on purpose (renewal, auth_revoked)."""
        try:
            self._connect_once()
        except StreamError as exc:
            _logger.warning("Firebase session stream failed: %s; %s", exc, _FALLBACK)
            return False
        except Exception:
            _logger.exception("Firebase session stream crashed; %s", _FALLBACK)
            return False
        return True

    def _connect_once(self) -> None:
        """One connection; returns only when it ended on purpose.

        Raises:
            StreamError: Auth, HTTP or protocol failure.
        """
        auth = stream_auth(_DEVICES_PREFIX)
        try:
            response = self._http.get(
                auth.url,
                params={"auth": auth.token},
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=_TIMEOUT_S,
            )
        except _STREAM_ERRORS as exc:
            msg = f"network error opening the stream: {exc}"
            raise StreamError(msg) from exc
        with response:
            if not response.ok:
                kind = (
                    "rejected (token or rules)"
                    if response.status_code in _HTTP_AUTH_REJECTED
                    else "failed"
                )
                msg = (
                    f"stream {kind}: HTTP {response.status_code} {response.text[:200]}"
                )
                raise StreamError(msg)
            _logger.info("Firebase session stream connected to %s", _DEVICES_PREFIX)
            self._consume(response, auth.renew_at)

    def _consume(self, response: requests.Response, renew_at: datetime) -> None:
        """Dispatch events until the server or the renew deadline ends it.

        Raises:
            StreamError: The stream broke, was cancelled or closed unasked.
        """
        meter = _ByteMeter()
        keepalives = 0
        try:
            for event in parse_sse(meter.lines(response)):
                if event.name == "keep-alive":
                    keepalives += 1
                    if keepalives <= _LOGGED_KEEPALIVES:
                        _logger.info("Session stream keep-alive #%d", keepalives)
                elif event.name in {"put", "patch"}:
                    self._dispatch(event, meter.total)
                elif event.name == "auth_revoked":
                    _logger.warning(
                        "Session stream token revoked/expired (%s); reconnecting",
                        event.data,
                    )
                    return
                elif event.name == "cancel":
                    msg = f"the database cancelled the stream ({event.data})"
                    raise StreamError(msg)
                else:
                    _logger.warning("Session stream ignored event %r", event.name)
                if datetime.now(UTC) >= renew_at:
                    _logger.info("Session stream renewing its ID token before expiry")
                    return
        except _STREAM_ERRORS as exc:
            msg = f"stream broke after {meter.total} bytes: {exc}"
            raise StreamError(msg) from exc
        msg = f"the server closed the stream after {meter.total} bytes"
        raise StreamError(msg)

    def _dispatch(self, event: SseEvent, total_bytes: int) -> None:
        """Hand one put/patch to the cache and log what it did."""
        try:
            result = self._cache.handle(event)
        except (ValueError, TypeError) as exc:
            _logger.warning("Session stream event undecodable (%s); %s", exc, _FALLBACK)
            return
        self._got_snapshot |= result.snapshot
        _logger.info(
            "Session stream %s (%d bytes read on this connection): %s",
            "snapshot" if result.snapshot else event.name,
            total_bytes,
            result.summary,
        )


class _ByteMeter:
    """Splits the raw stream into lines as bytes arrive, counting them."""

    def __init__(self) -> None:
        self.total = 0

    def lines(self, response: requests.Response) -> Iterator[str]:
        """Yield decoded lines without waiting for a full read buffer.

        ``iter_lines`` reads fixed-size chunks and would sit on a 30-byte
        keep-alive until more data came; ``read1`` returns what has arrived.
        """
        pending = b""
        while chunk := response.raw.read1(65536):
            self.total += len(chunk)
            *complete, pending = (pending + chunk).split(b"\n")
            for line in complete:
                yield line.rstrip(b"\r").decode("utf-8")
