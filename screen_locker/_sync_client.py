"""Building the sync client: Firebase only, proven live before it is returned.

Split out of :mod:`screen_locker._workout_sync` to keep every file under the
250-line cap. Re-exported from there, so callers and their patch targets are
unchanged.

``sync_client`` returning None means sync is OFF -- and says why in the log,
because a silent None here is exactly how the PC stopped syncing for weeks.

Firebase is the only transport since 2026-10-09. The GitHub mirror
(``kuhyx/syncs/screen-locker-sync``) is a frozen archive: nothing here reads
or writes it, and nothing deletes it. The PC used to refuse to push at all
without a GitHub PAT, even with Firebase configured -- so when the PAT was
lost, this machine silently published nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path

from crdt_sync import (
    CONFIG_FILE,
    ConfigError,
    FirebaseConfig,
    FirebaseCredentials,
    RemoteStore,
    RemoteSyncError,
    credential_store_for,
    firebase_client_for,
)
import requests

from screen_locker._constants import SYNC_TIMEOUT_SECONDS
from screen_locker._credential_recovery import RecoveryResult, recover_session
from screen_locker._degraded_sources import (
    DegradedSource,
    _record_degraded,
    clear_degraded_sources,
    degraded_sources,
)

_logger = logging.getLogger(__name__)

# Re-exported: these moved to _degraded_sources for the 250-line cap, but
# callers and tests still reach them as ``_sync_client.<name>``. __all__ keeps
# ruff from pruning the imports as unused -- same pattern the tests' conftest
# uses for its re-exported fixtures.
__all__ = [
    "DegradedSource",
    "clear_degraded_sources",
    "degraded_sources",
    "sync_client",
    "sync_client_or_reason",
    "try_recover_firebase_session",
]


def try_recover_firebase_session() -> RecoveryResult:
    """Rebuild our Firebase session from a sibling app's cached credential.

    The exchange itself lives here rather than in ``_credential_recovery`` so
    that module stays network-free and unit-testable; this wrapper supplies
    the one impure step.
    """

    def _mint(refresh_token: str) -> None:
        config = FirebaseConfig.load()
        # Exchange the borrowed token for our own session. Done against the
        # documented REST endpoint rather than through FirebaseTokenProvider,
        # whose only refresh entry point is private -- and reaching into a
        # library's privates is how a dependency bump breaks enforcement.
        response = requests.post(
            f"https://securetoken.googleapis.com/v1/token?key={config.api_key}",
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=SYNC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        store = credential_store_for("screen_locker")
        store.save(
            FirebaseCredentials(
                id_token=body["id_token"],
                refresh_token=body["refresh_token"],
                expires_at=datetime.now(tz=UTC)
                + timedelta(seconds=int(body["expires_in"])),
            )
        )

    return recover_session(
        config_root=Path.home() / ".config", app_name="screen_locker", mint=_mint
    )


# What a missing or broken Firebase costs, in both directions -- named in every
# warning so the journal says what is lost, not just that something failed.
_CONSEQUENCE = (
    "this PC's workouts will NOT be pushed and phone-logged workouts will "
    "NOT be pulled, so only ADB/HTTP can verify a phone workout here"
)


def _live_firebase_client() -> tuple[RemoteStore | None, str]:
    """Build the Firebase client, but only return one that actually answers.

    Constructing is not proving. ``firebase_client_for`` only asks
    ``has_session()``, which reads the cached JSON off disk and never touches
    the network, so a credential that is *present but rejected* builds
    perfectly and then 401s on every single read and write. That is exactly
    what happened on 2026-08-27: the recovery was wired to construction
    failures, the construction succeeded, and so the self-heal never fired
    while every operation was being refused.

    ``can_access_remote`` closes that gap with one authenticated round trip.
    It is documented never to raise -- a rejected token, a missing session, a
    bad URL and a dead network all report ``False`` -- so a probe failure is
    reported as a reason string rather than an exception.

    Returns:
        ``(client, "")`` when Firebase answered, else ``(None, reason)``.
    """
    try:
        client = firebase_client_for(
            "screen_locker", timeout_seconds=SYNC_TIMEOUT_SECONDS
        )
    except (ConfigError, RemoteSyncError) as exc:
        # The reason travels back to the caller, which decides whether to heal
        # or give up -- but it is logged here too, so the originating failure
        # is on the record even when a later recovery masks it.
        _logger.warning("Could not build the Firebase client: %s", exc)
        return None, str(exc)
    if not client.can_access_remote():
        return None, (
            "the cached Firebase credential was rejected by the server, or "
            "the database is unreachable — every read and write is refused"
        )
    return client, ""


def sync_client_or_reason() -> tuple[RemoteStore | None, str]:
    """Return a live Firebase client, or None and the reason there is none.

    The config file is checked before constructing anything, so an
    unconfigured machine never reaches the network. A configured but failing
    Firebase is healed from a sibling app's session when possible (waiting
    for a human to copy a JSON file is what cost 2026-06-12 and 2026-08-24 --
    two workouts done, two lockouts anyway); if that fails too, the failure is
    recorded as a degraded source so an empty pull is never reported as
    "no workouts".

    Returns:
        ``(client, "")`` on success, else ``(None, reason)`` -- ``reason`` is a
        sentence a caller can put straight into its own result.
    """
    if not CONFIG_FILE.is_file():
        reason = f"no Firebase config at {CONFIG_FILE}"
        _logger.warning("Sync is OFF: %s — %s", reason, _CONSEQUENCE)
        return None, reason
    client, reason = _live_firebase_client()
    if client is not None:
        return client, ""
    recovery = try_recover_firebase_session()
    if recovery.recovered:
        retried, retry_reason = _live_firebase_client()
        if retried is not None:
            _logger.info("Firebase recovered automatically: %s", recovery.reason)
            return retried, ""
        reason = f"still unusable after {recovery.reason}: {retry_reason}"
    else:
        reason = f"{reason}; automatic recovery failed: {recovery.reason}"
    _logger.warning(
        "Firebase is configured but unusable: %s — %s", reason, _CONSEQUENCE
    )
    _record_degraded("firebase", reason)
    return None, f"Firebase unusable: {reason}"


def sync_client() -> RemoteStore | None:
    """Return the live Firebase client, or None when sync cannot run.

    ``None`` is never silent: :func:`sync_client_or_reason` has already
    logged a warning naming the cause and what will not sync because of it.
    """
    client, _reason = sync_client_or_reason()
    return client
