"""Self-healing for a dead Firebase session, using credentials already here.

``crdt_sync`` caches a refresh token per app at
``~/.config/<app>/firebase_auth.json`` and falls back to the shared password
only when that cache is missing. On 2026-08-24 ``screen_locker`` had no cache
and the shared password had gone stale, so every run failed with
``INVALID_LOGIN_CREDENTIALS`` -- while ``diet_guard`` and ``wake_alarm`` sat
in sibling directories holding live refresh tokens for the *same* account and
the *same* project, refreshed minutes earlier.

Every app here signs in as one personal account against one project (see
``~/.config/crdt-sync/firebase.json``), so any sibling's refresh token mints a
valid session for us. That makes this recovery purely local: no password, no
browser, no human. The alternative -- a person copying a JSON file between
directories -- is a habit, not a fix, and habits are what failed twice.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING

from crdt_sync import ConfigError, RemoteSyncError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_logger = logging.getLogger(__name__)

_CACHE_NAME = "firebase_auth.json"


@dataclass(frozen=True)
class RecoveryResult:
    """What a recovery attempt did, and why.

    ``reason`` always reads like a sentence: this runs unattended inside a
    systemd unit, so the journal line is the only thing a human will ever see.
    """

    recovered: bool
    reason: str
    donor: str | None = None


def find_sibling_refresh_token(
    config_root: Path, *, skip: str
) -> tuple[str, str] | None:
    """Return ``(app_name, refresh_token)`` from a sibling app's cache.

    Args:
        config_root: The directory holding per-app config dirs (``~/.config``).
        skip: Our own app name, whose cache is the thing being replaced.

    Returns:
        The first usable sibling credential, or ``None`` when none exists.
    """
    if not config_root.is_dir():
        return None
    for cache in sorted(config_root.glob(f"*/{_CACHE_NAME}")):
        app_name = cache.parent.name
        if app_name == skip:
            continue
        try:
            data = json.loads(cache.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            # One corrupt sibling must not hide the healthy ones behind it.
            _logger.warning(
                "Skipping unreadable credential cache %s: %s — continuing the "
                "search for another app's live refresh token",
                cache,
                exc,
            )
            continue
        token = data.get("refresh_token")
        if isinstance(token, str) and token:
            return app_name, token
    return None


def recover_session(
    *,
    config_root: Path,
    app_name: str,
    mint: Callable[[str], None],
) -> RecoveryResult:
    """Rebuild our Firebase session from a sibling app's refresh token.

    ``mint`` is injected rather than imported so this module stays free of
    network code and the tests never reach Firebase.

    Args:
        config_root: The directory holding per-app config dirs.
        app_name: Our app name, both the skip target and the cache we write.
        mint: Exchanges a refresh token for a session and persists it.
    """
    found = find_sibling_refresh_token(config_root, skip=app_name)
    if found is None:
        reason = (
            f"no sibling app under {config_root} holds a Firebase refresh "
            "token, so the session cannot be rebuilt locally — sign in once "
            "on this machine to seed one"
        )
        _logger.warning("Firebase recovery failed: %s", reason)
        return RecoveryResult(recovered=False, reason=reason)

    donor, refresh_token = found
    try:
        mint(refresh_token)
    except (OSError, ValueError, RuntimeError, ConfigError, RemoteSyncError) as exc:
        reason = f"borrowed {donor}'s refresh token but it was rejected: {exc}"
        _logger.warning("Firebase recovery failed: %s", reason)
        return RecoveryResult(recovered=False, reason=reason)

    _logger.info(
        "Firebase session rebuilt for %s from %s's cached refresh token — no "
        "password or human step was needed",
        app_name,
        donor,
    )
    return RecoveryResult(
        recovered=True,
        reason=f"rebuilt the session from {donor}'s cached refresh token",
        donor=donor,
    )
