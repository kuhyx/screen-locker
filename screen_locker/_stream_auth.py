"""The ID token and URL for the Firebase session stream.

Split out of :mod:`screen_locker._session_stream` for the 250-line cap.
Reuses crdt_sync's own token provider and the screen_locker credential cache
(``~/.config/screen_locker/firebase_auth.json``); it never signs in with the
password, which is stale -- only the cached refresh token authenticates. A
missing session is healed the way the sync heals it,
:func:`screen_locker._sync_client.try_recover_firebase_session`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from crdt_sync import (
    ConfigError,
    FirebaseAuthError,
    FirebaseConfig,
    FirebaseTokenProvider,
    credential_store_for,
)
from crdt_sync._firebase import encode_path

from screen_locker._sync_client import try_recover_firebase_session

__all__ = ["StreamAuth", "StreamError", "stream_auth"]

_APP: Final = "screen_locker"
# Inside crdt_sync's 5-minute refresh skew, so the reconnect mints a new token
# instead of being handed the dying one back.
_RENEW_BEFORE_EXPIRY: Final = timedelta(minutes=4)
_ASSUMED_LIFETIME: Final = timedelta(hours=1)


class StreamError(Exception):
    """One stream connection failed in a way that warrants backing off."""


@dataclass(frozen=True)
class StreamAuth:
    """Where to stream from, with which token, and when to renew it."""

    url: str
    token: str
    renew_at: datetime


def _provider(config: FirebaseConfig) -> FirebaseTokenProvider:
    """A provider over the cached session, recovering one if there is none.

    Raises:
        StreamError: No cached session, and recovery failed too.
    """
    store = credential_store_for(_APP)
    auth = FirebaseTokenProvider(config.api_key, store)
    if auth.has_session():
        return auth
    recovery = try_recover_firebase_session()
    if not recovery.recovered:
        msg = f"no cached Firebase session and recovery failed: {recovery.reason}"
        raise StreamError(msg)
    return FirebaseTokenProvider(config.api_key, store)


def stream_auth(path: str) -> StreamAuth:
    """A fresh token for streaming ``path`` (a logical RTDB path).

    A new provider per call re-reads the cache, so a token the 15-min sync
    refreshed in the meantime is picked up rather than refreshed again.

    Raises:
        StreamError: The config, the session or the token is unusable.
    """
    try:
        config = FirebaseConfig.load()
    except ConfigError as exc:
        msg = f"Firebase config unusable: {exc}"
        raise StreamError(msg) from exc
    auth = _provider(config)
    try:
        token = auth.id_token()
    except FirebaseAuthError as exc:
        msg = f"could not get an ID token: {exc}"
        raise StreamError(msg) from exc
    saved = credential_store_for(_APP).load()
    expires = saved.expires_at if saved else datetime.now(UTC) + _ASSUMED_LIFETIME
    return StreamAuth(
        url=f"{config.database_url.rstrip('/')}/{encode_path(path)}.json",
        token=token,
        renew_at=expires - _RENEW_BEFORE_EXPIRY,
    )
