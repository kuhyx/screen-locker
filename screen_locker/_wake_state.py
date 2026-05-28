"""Read wake-alarm state to check if a workout skip was earned today.

This module reads the JSON state file written by the companion wake_alarm
service.  It does not import wake_alarm directly — the two packages
communicate only through the shared state file on disk.

The state file path defaults to WAKE_STATE_FILE in _constants.py, which
points to the sibling wake_alarm package directory.  Override it in tests
by patching ``screen_locker._wake_state.WAKE_STATE_FILE``.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from screen_locker._constants import WAKE_STATE_FILE
from screen_locker._log_integrity import verify_entry_hmac

_logger = logging.getLogger(__name__)


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def load_wake_state() -> dict[str, object] | None:
    """Load and verify today's wake state.

    Returns the state dict if it exists, is valid (HMAC OK), and is
    for today.  Returns None otherwise.
    """
    if not WAKE_STATE_FILE.exists():
        return None

    try:
        with WAKE_STATE_FILE.open() as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        _logger.warning("Cannot read wake state file")
        return None

    if not isinstance(state, dict):
        return None

    if state.get("date") != _today_str():
        return None

    if not verify_entry_hmac(state):
        _logger.warning("Wake state HMAC verification failed")
        return None

    return state


def has_workout_skip_today() -> bool:
    """Check if the user earned a workout skip for today."""
    state = load_wake_state()
    if state is None:
        return False
    return bool(state.get("skip_workout"))
