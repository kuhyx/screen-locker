"""HMAC-based integrity checking for workout log entries."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets

from python_pkg.screen_locker._constants import HMAC_KEY_FILE

_logger = logging.getLogger(__name__)


def _load_hmac_key() -> bytes | None:
    """Load HMAC key from the root-owned key file.

    Returns the key bytes, or None if the file cannot be read.
    """
    try:
        return HMAC_KEY_FILE.read_bytes().strip()
    except OSError:
        _logger.warning("Cannot read HMAC key from %s", HMAC_KEY_FILE)
        return None


def _generate_hmac_key() -> bytes | None:
    """Generate a new HMAC key and write it to the key file.

    The key file must be writable (requires root or setup script).
    Returns the new key bytes, or None on failure.
    """
    key = secrets.token_bytes(32)
    try:
        HMAC_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HMAC_KEY_FILE.write_bytes(key)
    except OSError:
        _logger.warning("Cannot write HMAC key to %s", HMAC_KEY_FILE)
        return None
    return key


def compute_entry_hmac(entry_data: dict[str, object]) -> str | None:
    """Compute HMAC-SHA256 for a workout log entry.

    Args:
        entry_data: The log entry dict (without the 'hmac' field).

    Returns:
        Hex-encoded HMAC string, or None if the key is unavailable.
    """
    key = _load_hmac_key()
    if key is None:
        return None
    payload = json.dumps(entry_data, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def verify_entry_hmac(entry: dict[str, object]) -> bool:
    """Verify HMAC signature of a workout log entry.

    Args:
        entry: The full log entry dict including the 'hmac' field.

    Returns:
        True if the HMAC is valid, False if invalid or key unavailable.
    """
    stored_hmac = entry.get("hmac")
    if not isinstance(stored_hmac, str):
        return False
    key = _load_hmac_key()
    if key is None:
        return False
    entry_without_hmac = {k: v for k, v in entry.items() if k != "hmac"}
    payload = json.dumps(entry_without_hmac, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(stored_hmac, expected)
