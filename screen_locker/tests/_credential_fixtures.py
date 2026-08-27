"""Helpers for the credential-recovery tests.

Shared because ``test_credential_recovery.py`` had to be split at the
250-line cap and both halves build the same on-disk credential caches.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def write_cache(path: Path, refresh_token: str, *, expires_at: str) -> None:
    """Write a credential cache shaped like ``FileCredentialStore``'s."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id_token": "stale-id-token",
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "local_id": "uid-1",
            }
        )
    )
