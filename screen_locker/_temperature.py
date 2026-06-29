"""Temperature fetching via wttr.in for the heat-skip feature.

Pure logic — no Tk imports. Always fetches from the API; never trusts
user claims about the temperature.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

_logger = logging.getLogger(__name__)

_WTTR_URL = "https://wttr.in/{city}?format=j1"
_TIMEOUT_SECONDS = 5


def fetch_current_temp_celsius(city: str) -> float | None:
    """Return the current temperature in °C for *city*, or None on failure.

    Uses wttr.in's JSON API (no API key required). Returns None on network
    errors, timeouts, or unexpected response shapes so callers can fail-closed.
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


def is_too_hot(city: str, threshold: float) -> float | None:
    """Return the current temperature if it exceeds *threshold*, else None.

    Fail-closed: API unavailable → returns None → no heat skip offered.
    """
    temp = fetch_current_temp_celsius(city)
    if temp is None:
        return None
    return temp if temp >= threshold else None
