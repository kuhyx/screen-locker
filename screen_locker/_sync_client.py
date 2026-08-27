"""Building the sync client: read the token, pick Firebase or the GitHub mirror.

Split out of :mod:`screen_locker._workout_sync` to keep every file under the
250-line cap. Re-exported from there, so callers and their patch targets are
unchanged.

``sync_client`` returning None means sync is OFF -- and says why in the log,
because a silent None here is exactly how the PC stopped syncing for weeks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path

from crdt_sync import (
    CONFIG_FILE,
    ConfigError,
    FirebaseAuthError,
    FirebaseConfig,
    FirebaseCredentials,
    GitHubSyncClient,
    RemoteStore,
    RemoteSyncError,
    credential_store_for,
    firebase_client_for,
    mirror_client_for,
)
import requests

from screen_locker._constants import (
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TIMEOUT_SECONDS,
    SYNC_TOKEN_FILE,
)
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
    "read_sync_token",
    "remote_client",
    "sync_client",
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
                expires_at=datetime.now(tz=timezone.utc)
                + timedelta(seconds=int(body["expires_in"])),
            )
        )

    return recover_session(
        config_root=Path.home() / ".config", app_name="screen_locker", mint=_mint
    )


def read_sync_token() -> str | None:
    """Return the saved sync PAT, or None if sync isn't configured.

    Unlike diet_guard's equivalent, an absent or empty token file is a
    normal state here -- sync is an optional primary channel, not something
    the app requires to function.
    """
    if not SYNC_TOKEN_FILE.exists():
        return None
    token = SYNC_TOKEN_FILE.read_text().strip()
    return token or None


def _live_mirror_client(github: RemoteStore) -> tuple[RemoteStore | None, str]:
    """Build the mirrored client, but only return one that actually answers.

    Constructing is not proving. ``mirror_client_for`` only asks
    ``has_session()``, which reads the cached JSON off disk and never touches
    the network, so a credential that is *present but rejected* builds
    perfectly and then 401s on every single read and write. That is exactly
    what happened on 2026-08-27: the recovery below was wired to construction
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
        client = mirror_client_for("screen_locker", github)
    except (ConfigError, FirebaseAuthError, RemoteSyncError) as exc:
        # The reason travels back to the caller, which decides whether to heal
        # or degrade -- but it is logged here too, so the originating failure
        # is on the record even when a later recovery masks it.
        _logger.warning("Could not build the Firebase client: %s", exc)
        return None, str(exc)
    if not client.can_access_remote():
        return None, (
            "the cached Firebase credential was rejected by the server — it "
            "exists on disk, so nothing failed while connecting, but every "
            "read and write is being refused"
        )
    return client, ""


def remote_client(github: RemoteStore) -> RemoteStore:
    """Return the backend to read the phone's workout log from.

    Firebase when ``~/.config/crdt-sync/`` is set up, with GitHub kept as a
    mirror so a phone that has not moved yet is still seen; GitHub alone
    otherwise. :class:`MirrorSyncClient` reads the union of both, so a workout
    logged against either backend still counts.

    Not read-only: ``_manual_push.push_pc_workouts`` writes this machine's log
    through the client this returns. That matters for the degraded path --
    when Firebase is dropped here the push still lands on GitHub, which the
    phone also reads, so records are not lost; ``_manual_push`` reports the
    push as INCOMPLETE rather than letting a half-landed push look clean.

    The config file is checked before constructing anything, so an
    unconfigured machine never reaches the network.

    Rolling back is deleting this function and passing ``github`` straight
    through: no data moves either way.
    """
    if not CONFIG_FILE.is_file():
        return github
    usable, reason = _live_mirror_client(github)
    if usable is not None:
        return usable
    # Before degrading, try to heal: a sibling app on this machine almost
    # certainly holds a live refresh token for the same account. Waiting
    # for a human to copy a JSON file is what cost 2026-06-12 and
    # 2026-08-24 -- two workouts done, two lockouts anyway.
    recovery = try_recover_firebase_session()
    if recovery.recovered:
        retried, retry_reason = _live_mirror_client(github)
        if retried is not None:
            _logger.info("Firebase recovered automatically: %s", recovery.reason)
            return retried
        _logger.warning(
            "Firebase still unusable after %s: %s", recovery.reason, retry_reason
        )
        _record_degraded("firebase", retry_reason)
        return github
    _logger.warning(
        "Firebase unavailable, reading workouts via GitHub only: %s — the "
        "phone syncs to Firebase, so a workout logged there is INVISIBLE "
        "on this machine until this is fixed. Automatic recovery also "
        "failed: %s",
        reason,
        recovery.reason,
    )
    _record_degraded("firebase", f"{reason}; recovery: {recovery.reason}")
    return github


def sync_client() -> RemoteStore | None:
    """Return the configured read client, or None if sync is set up nowhere.

    A GitHub token is no longer required: Firebase has been the primary backend
    since eb4ff01, so a Firebase-only machine must still sync. Previously this
    module returned early whenever the PAT was missing, reporting "sync is OFF"
    on a machine whose sync was working perfectly -- a false negative that hid
    a live backend behind a legacy credential check.

    GitHub is used alone when only the PAT exists, Firebase alone when only
    ``~/.config/crdt-sync/`` exists, and the mirrored union when both do.
    ``None`` means neither is configured, which stays a benign, expected state.
    """
    token = read_sync_token()
    github = (
        GitHubSyncClient(
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
            token,
            timeout_seconds=SYNC_TIMEOUT_SECONDS,
        )
        if token is not None
        else None
    )
    if github is not None:
        return remote_client(github)
    if not CONFIG_FILE.is_file():
        _logger.warning(
            "Cannot pull synced workouts: no sync token at %s and no Firebase "
            "config at %s — sync is OFF, so only ADB/HTTP can verify a phone "
            "workout and phone-logged workouts will NOT count here",
            SYNC_TOKEN_FILE,
            CONFIG_FILE,
        )
        return None
    try:
        return firebase_client_for("screen_locker")
    except (ConfigError, FirebaseAuthError, RemoteSyncError) as exc:
        _logger.warning(
            "Firebase is configured at %s but unusable, and there is no GitHub "
            "token at %s to fall back to: %s — pulling NO synced workouts",
            CONFIG_FILE,
            SYNC_TOKEN_FILE,
            exc,
        )
        return None
