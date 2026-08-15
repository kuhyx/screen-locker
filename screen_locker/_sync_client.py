"""Building the sync client: read the token, pick Firebase or the GitHub mirror.

Split out of :mod:`screen_locker._workout_sync` to keep every file under the
250-line cap. Re-exported from there, so callers and their patch targets are
unchanged.

``sync_client`` returning None means sync is OFF -- and says why in the log,
because a silent None here is exactly how the PC stopped syncing for weeks.
"""

from __future__ import annotations

import logging

from crdt_sync import (
    CONFIG_FILE,
    ConfigError,
    FirebaseAuthError,
    GitHubSyncClient,
    RemoteStore,
    RemoteSyncError,
    firebase_client_for,
    mirror_client_for,
)

from screen_locker._constants import (
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TIMEOUT_SECONDS,
    SYNC_TOKEN_FILE,
)

_logger = logging.getLogger(__name__)


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
        _logger.warning(
            "Firebase unavailable, reading workouts via GitHub only: %s", exc
        )
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
