"""HMAC-based integrity checking — re-exports from shared package."""

from __future__ import annotations

from python_pkg.shared.log_integrity import (
    HMAC_KEY_FILE,
    _generate_hmac_key,
    _load_hmac_key,
    compute_entry_hmac,
    verify_entry_hmac,
)

__all__ = [
    "HMAC_KEY_FILE",
    "_generate_hmac_key",
    "_load_hmac_key",
    "compute_entry_hmac",
    "verify_entry_hmac",
]
