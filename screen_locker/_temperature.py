"""Temperature fetching via wttr.in for the heat-skip feature.

Pure logic — no Tk imports. Always fetches from the API; never trusts
user claims about the temperature.
"""

from __future__ import annotations

from concurrent.futures import Future
from concurrent.futures import TimeoutError as _FutureTimeoutError
from dataclasses import dataclass
import http.client
import json
import logging
import threading
from typing import TYPE_CHECKING
import urllib.error
import urllib.request

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_WTTR_URL = "https://wttr.in/{city}?format=j1"
_TIMEOUT_SECONDS = 4
# urlopen's `timeout` bounds the socket connect/read, but not necessarily DNS
# resolution (`getaddrinfo`) on every platform/resolver — a stalled resolver
# can block far past `_TIMEOUT_SECONDS` with no visible failure. This is a
# second, hard wall-clock ceiling enforced independently in a worker thread.
# 5.0 is the whole budget the locker is allowed to spend deciding whether it
# is too hot to train; the socket timeout is set below it so the ordinary
# network path fails first and reports *why* rather than just "too slow".
HARD_TIMEOUT_SECONDS = 5.0

# Everything `urlopen` + `json.loads` + the subscripting below can raise.
# Spelled out rather than caught as a blind `except Exception`, which ruff
# rejects (BLE001) and which this repo has no escape hatch for.
# `http.client.HTTPException` (IncompleteRead, BadStatusLine, ...) is the
# one that used to be missing: it inherits Exception, *not* OSError, so it
# escaped this function, escaped `future.result()` (which only catches the
# timeout), and killed the locker before it could record its decision — a
# lock that silently never happened.
_FETCH_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    OSError,
    http.client.HTTPException,
    json.JSONDecodeError,
    KeyError,
    IndexError,
    ValueError,
)


@dataclass(frozen=True)
class TemperatureCheck:
    """Result of a bounded live temperature fetch."""

    temp_celsius: float | None
    timed_out: bool


def submit_background[T](fn: Callable[[], T]) -> Future[T]:
    """Run *fn* on a daemon thread and return a Future for its result.

    Deliberately not a ``ThreadPoolExecutor``. Its worker threads are
    non-daemon and joined by an interpreter-exit hook, so a genuinely stuck
    DNS lookup kept the locker's process alive past ``sys.exit(0)`` — the
    hard timeout below returned on time while the process did not. A daemon
    thread is abandoned at exit, which is the correct behaviour for a
    fire-and-forget diagnostic read.

    Args:
        fn: The zero-argument callable to run off the calling thread.

    Returns:
        A Future that resolves when *fn* returns.
    """
    future: Future[T] = Future()

    def _run() -> None:
        try:
            future.set_result(fn())
        except _FETCH_ERRORS as exc:
            # Never reachable via _fetch_current_temp_celsius_unbounded, which
            # handles these itself; here so a future caller cannot turn a
            # background thread into a future that resolves to nothing.
            _logger.warning("Background fetch failed: %s", exc)
            future.set_exception(exc)

    threading.Thread(target=_run, daemon=True, name="temperature-fetch").start()
    return future


def _fetch_current_temp_celsius_unbounded(city: str) -> float | None:
    """Return the current temperature in °C for *city*, or None on failure.

    Uses wttr.in's JSON API (no API key required). Returns None on network
    errors, timeouts, or unexpected response shapes so callers can fail-closed.
    May block past `_TIMEOUT_SECONDS` if DNS resolution stalls — callers
    should go through `fetch_current_temp_with_status` for a hard bound
    instead of calling this directly.

    Args:
        city: The city name to look up, URL-quoted before use.

    Returns:
        The temperature in °C, or None if it could not be determined.
    """
    url = _WTTR_URL.format(city=urllib.request.quote(city, safe=""))
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
        temp_str = data["current_condition"][0]["temp_C"]
        return float(temp_str)
    except _FETCH_ERRORS as exc:
        _logger.warning(
            "Temperature fetch failed (%s: %s) — the caller must fail closed "
            "and lock rather than treat this as 'not hot'",
            type(exc).__name__,
            exc,
        )
        return None


def fetch_current_temp_with_status(
    city: str, *, hard_timeout: float = HARD_TIMEOUT_SECONDS
) -> TemperatureCheck:
    """Fetch °C for *city*, bounded to *hard_timeout* seconds wall-clock.

    Runs the fetch on a daemon thread and stops waiting on it after
    *hard_timeout* regardless of what the network call is doing internally
    (DNS, connect, read). The thread itself can't be killed and may keep
    running in the background after we give up on it — acceptable for a
    fire-and-forget diagnostic read, and harmless at exit because it is a
    daemon. Distinguishes "timed out" from other failures (network/parse
    errors) so callers can report which happened.

    Args:
        city: The city name to look up.
        hard_timeout: Wall-clock ceiling in seconds.

    Returns:
        The temperature and whether the wall-clock ceiling was hit.
    """
    future = submit_background(lambda: _fetch_current_temp_celsius_unbounded(city))
    try:
        temp = future.result(timeout=hard_timeout)
    except _FutureTimeoutError:
        _logger.warning(
            "Temperature fetch exceeded hard timeout of %.1fs — the caller "
            "must fail closed and lock rather than treat this as 'not hot'",
            hard_timeout,
        )
        return TemperatureCheck(temp_celsius=None, timed_out=True)
    except _FETCH_ERRORS as exc:
        _logger.warning(
            "Temperature fetch raised past its own handler (%s: %s) — "
            "reporting failure so the caller fails closed and locks",
            type(exc).__name__,
            exc,
        )
        return TemperatureCheck(temp_celsius=None, timed_out=False)
    return TemperatureCheck(temp_celsius=temp, timed_out=False)
