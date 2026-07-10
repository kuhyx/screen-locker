"""Temperature fetching via wttr.in for the heat-skip feature.

Pure logic — no Tk imports. Always fetches from the API; never trusts
user claims about the temperature.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeoutError
from dataclasses import dataclass
import json
import logging
import urllib.error
import urllib.request

_logger = logging.getLogger(__name__)

_WTTR_URL = "https://wttr.in/{city}?format=j1"
_TIMEOUT_SECONDS = 5
# urlopen's `timeout` bounds the socket connect/read, but not necessarily DNS
# resolution (`getaddrinfo`) on every platform/resolver — a stalled resolver
# can block far past `_TIMEOUT_SECONDS` with no visible failure. This is a
# second, hard wall-clock ceiling enforced independently in a worker thread.
HARD_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class TemperatureCheck:
    """Result of a bounded live temperature fetch."""

    temp_celsius: float | None
    timed_out: bool


def _fetch_current_temp_celsius_unbounded(city: str) -> float | None:
    """Return the current temperature in °C for *city*, or None on failure.

    Uses wttr.in's JSON API (no API key required). Returns None on network
    errors, timeouts, or unexpected response shapes so callers can fail-closed.
    May block past `_TIMEOUT_SECONDS` if DNS resolution stalls — callers
    should go through `fetch_current_temp_with_status` for a hard bound
    instead of calling this directly.
    """
    url = _WTTR_URL.format(city=urllib.request.quote(city, safe=""))
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
        temp_str = data["current_condition"][0]["temp_C"]
        return float(temp_str)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _logger.warning("Temperature fetch failed (network): %s", exc)
        return None
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        _logger.warning("Temperature fetch failed (parse): %s", exc)
        return None


def fetch_current_temp_with_status(
    city: str, *, hard_timeout: float = HARD_TIMEOUT_SECONDS
) -> TemperatureCheck:
    """Fetch °C for *city*, bounded to *hard_timeout* seconds wall-clock.

    Runs the fetch in a worker thread and stops waiting on it after
    *hard_timeout* regardless of what the network call is doing internally
    (DNS, connect, read). The worker thread itself can't be killed and may
    keep running in the background after we give up on it — acceptable for
    a fire-and-forget diagnostic read. Distinguishes "timed out" from other
    failures (network/parse errors) so callers can report which happened.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_fetch_current_temp_celsius_unbounded, city)
    executor.shutdown(wait=False)
    try:
        temp = future.result(timeout=hard_timeout)
    except _FutureTimeoutError:
        _logger.warning(
            "Temperature fetch exceeded hard timeout of %.1fs", hard_timeout
        )
        return TemperatureCheck(temp_celsius=None, timed_out=True)
    return TemperatureCheck(temp_celsius=temp, timed_out=False)
