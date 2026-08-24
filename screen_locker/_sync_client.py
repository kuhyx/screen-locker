"""Building the sync client: read the token, pick Firebase or the GitHub mirror.

Split out of :mod:`screen_locker._workout_sync` to keep every file under the
250-line cap. Re-exported from there, so callers and their patch targets are
unchanged.

``sync_client`` returning None means sync is OFF -- and says why in the log,
because a silent None here is exactly how the PC stopped syncing for weeks.
"""

from __future__ import annotations

from dataclasses import dataclass
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

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DegradedSource:
    """A workout backend that could not be read on this run.

    ``reason`` is the backend's own error text, kept verbatim so the status
    view and the lock decision can quote something actionable rather than a
    generic "sync problem".
    """

    name: str
    reason: str


# Process-scoped rather than persisted: it describes THIS run's ability to
# read, and a stale marker from an earlier run would be worse than none. The
# lock chain and the pull both happen in one process, so this survives exactly
# as long as it is true.
_degraded: list[DegradedSource] = []


def degraded_sources() -> list[DegradedSource]:
    """Return the backends that failed to answer during this run."""
    return list(_degraded)


def clear_degraded_sources() -> None:
    """Forget recorded failures (called at the start of a fresh check)."""
    _degraded.clear()


def _record_degraded(name: str, reason: str) -> None:
    """Note that *name* could not be read, so callers can stop guessing.

    Logging alone was not enough: on 2026-08-24 the warning was emitted, the
    Firebase read was skipped, and the lock decision still reported
    "0 workouts this week" as though the source had answered "none".
    """
    _degraded.append(DegradedSource(name, reason))


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


def remote_client(github: RemoteStore) -> RemoteStore:
    """Return the backend to read the phone's workout log from.

    Firebase when ``~/.config/crdt-sync/`` is set up, with GitHub kept as a
    mirror so a phone that has not moved yet is still seen; GitHub alone
    otherwise. Both callers here are read-only pulls -- this side never pushes
    -- and :class:`MirrorSyncClient` reads the union of both, so a workout
    logged against either backend still counts.

    The config file is checked before constructing anything, so an
    unconfigured machine never reaches the network.

    Rolling back is deleting this function and passing ``github`` straight
    through: no data moves either way.
    """
    if not CONFIG_FILE.is_file():
        return github
    try:
        return mirror_client_for("screen_locker", github)
    except (ConfigError, FirebaseAuthError, RemoteSyncError) as exc:
        # Before degrading, try to heal: a sibling app on this machine almost
        # certainly holds a live refresh token for the same account. Waiting
        # for a human to copy a JSON file is what cost 2026-06-12 and
        # 2026-08-24 -- two workouts done, two lockouts anyway.
        recovery = try_recover_firebase_session()
        if recovery.recovered:
            try:
                client = mirror_client_for("screen_locker", github)
            except (ConfigError, FirebaseAuthError, RemoteSyncError) as retry_exc:
                _logger.warning(
                    "Firebase still unusable after %s: %s", recovery.reason, retry_exc
                )
                _record_degraded("firebase", str(retry_exc))
                return github
            _logger.info("Firebase recovered automatically: %s", recovery.reason)
            return client
        _logger.warning(
            "Firebase unavailable, reading workouts via GitHub only: %s — the "
            "phone syncs to Firebase, so a workout logged there is INVISIBLE "
            "on this machine until this is fixed. Automatic recovery also "
            "failed: %s",
            exc,
            recovery.reason,
        )
        _record_degraded("firebase", f"{exc}; recovery: {recovery.reason}")
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
