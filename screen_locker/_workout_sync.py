"""Pulls phone/other-device workouts via crdt-sync's GitHub transport.

GitHub is used purely as dumb file storage (see ``crdt_sync``'s own docs) --
the phone app pushes its completed-workout log to a private repo; this module
reads the session log and every device's manual-workout records. (The PC does
push its OWN manual workouts, but via :mod:`screen_locker._manual_push`, not
here.) Sync is optional: an unconfigured token is a normal, expected state,
not an error -- unlike diet_guard, where sync is core to the app.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from crdt_sync import (
    CONFIG_FILE,
    ConfigError,
    FirebaseAuthError,
    GitHubSyncClient,
    Hlc,
    Record,
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
from screen_locker._manual_workout import MANUAL_WORKOUT_SYNC_KIND
from screen_locker._sync_retry import with_sync_retry

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_DEVICES_PREFIX = "screen-locker-sync/devices"
_PAYLOAD_FIELD = "payload"


def _is_manual_payload(payload: object) -> bool:
    """True if a decoded sync payload is a manual-workout record."""
    return isinstance(payload, dict) and payload.get("kind") == MANUAL_WORKOUT_SYNC_KIND


def _is_session_payload(payload: object) -> bool:
    """True if a decoded sync payload is a completed StrongLifts session.

    Identified by SHAPE -- the presence of ``exercises`` -- not by a ``kind``
    field, because the phone app's ``WorkoutSession.toJson()`` emits no ``kind``
    at all. Keying session detection on ``kind`` is what made real sessions
    invisible to the only reader that walks every device directory.

    Shape-matching also excludes the PC-origin ``runnerup_verified`` /
    ``phone_verified`` records that share these device logs: they are non-manual
    too, so "not manual" alone would hand a caller expecting ``exercises`` and
    ``duration_seconds`` a record that has neither.
    """
    return isinstance(payload, dict) and isinstance(payload.get("exercises"), list)


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


def _merge_device_records(
    client: RemoteStore,
    extract: Callable[[str], dict[str, tuple[dict, Hlc]]],
    what: str,
    *,
    strict: bool = False,
) -> dict[str, tuple[dict, Hlc]]:
    """Merge ``extract``-selected records across EVERY device log.

    Walks ``devices/<id>/log.json`` for every device directory, keeping the
    highest-HLC copy of each record id -- records are id-stable, so the same
    workout mirrored into two device logs dedups to one.

    Every device is walked because the phone's directory name is a per-install
    uuid (since ffc6c72), not a fixed role id: it changes on every reinstall,
    and old directories linger. Reading any single hardcoded device path is
    guaranteed to go stale, which is exactly how phone sessions stopped
    reaching this machine.

    Best-effort per device: an unreachable or corrupt device log yields fewer
    records rather than raising, and says so at ``warning`` -- naming the
    device and what is being dropped -- so a partial pull is never silent.

    ``strict`` controls only the *top-level* listing failure, where nothing at
    all could be read. Callers that distinguish "nothing to sync" from "the
    sync broke" pass ``strict=True`` to get the exception instead of an empty
    dict, since an empty dict would otherwise report a total failure as the
    benign "no records" case.
    """
    try:
        devices = with_sync_retry(
            lambda: client.list_directory(_DEVICES_PREFIX),
            description="list synced device logs",
        )
    except RemoteSyncError as exc:
        _logger.warning(
            "Could not list device logs under %s in %s/%s: %s — pulling NO "
            "synced %s, so phone-logged workouts will not count",
            _DEVICES_PREFIX,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
            exc,
            what,
        )
        if strict:
            raise
        return {}

    merged: dict[str, tuple[dict, Hlc]] = {}
    for device in devices:
        path = f"{_DEVICES_PREFIX}/{device}/log.json"
        try:
            text = client.get_file_text(path)
        except RemoteSyncError as exc:
            _logger.warning(
                "Could not fetch device log %s: %s — SKIPPING that device, so "
                "any %s it holds will not count",
                path,
                exc,
                what,
            )
            continue
        if text is None:
            continue
        try:
            records = extract(text)
        except (ValueError, KeyError, TypeError) as exc:
            _logger.warning("Corrupt sync data at %s: %s", path, exc)
            continue
        for rid, (payload, hlc) in records.items():
            existing = merged.get(rid)
            if existing is None or existing[1] < hlc:
                merged[rid] = (payload, hlc)

    return merged


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


def pull_synced_workout() -> tuple[dict | None, str | None]:
    """Return ``(data, error)``: the last-synced StrongLifts session, if any.

    Merges sessions across EVERY device directory and returns the highest-HLC
    one. It used to read a single hardcoded ``devices/phone/log.json``, which
    silently went stale the moment the phone moved to a per-install uuid
    (ffc6c72): this machine kept happily returning a session from 2026-07-27
    while newer ones sat unread one directory over.

    - Nothing configured anywhere: ``(None, None)`` -- benign, sync is optional.
    - Nothing pushed yet: ``(None, None)``.
    - A real sync error (network, bad token, backend unreachable):
      ``(None, <message>)``.
    - Success: ``(payload_dict, None)``.
    """
    client = sync_client()
    if client is None:
        return None, None

    try:
        merged = _merge_device_records(
            client, _session_records, "StrongLifts sessions", strict=True
        )
    except RemoteSyncError as exc:
        _logger.warning(
            "Could not fetch synced workout logs under %s: %s — falling back "
            "to ADB/HTTP verification",
            _DEVICES_PREFIX,
            exc,
        )
        return None, str(exc)

    if not merged:
        return None, None

    _rid, (payload, _hlc) = max(merged.items(), key=lambda item: item[1][1])
    return payload, None


def _session_records(log_json: str) -> dict[str, tuple[dict, Hlc]]:
    """Return ``{record_id: (payload, hlc)}`` for session records in a log blob.

    Raises the same decode errors as :func:`_manual_records`; callers treat a
    corrupt device log as "no sessions from that device".
    """
    return _records_matching(log_json, _is_session_payload)


def _records_matching(
    log_json: str, predicate: Callable[[object], bool]
) -> dict[str, tuple[dict, Hlc]]:
    """Return ``{record_id: (payload, hlc)}`` for payloads passing ``predicate``.

    Raises:
        TypeError: If the top-level JSON isn't an object or a record's shape
            doesn't match what :meth:`Record.from_dict` expects.
        KeyError: If a record is missing an expected key.
        ValueError: Via ``json.loads`` or :meth:`crdt_sync.Hlc.from_str`.
    """
    raw = json.loads(log_json)
    if not isinstance(raw, dict):
        msg = f"top-level sync payload is not a JSON object: {raw!r}"
        raise TypeError(msg)
    result: dict[str, tuple[dict, Hlc]] = {}
    for data in raw.values():
        record = Record.from_dict(data)
        field = record.fields.get(_PAYLOAD_FIELD)
        if field is None:
            continue
        payload, hlc = field
        if predicate(payload):
            result[record.id] = (payload, hlc)
    return result


def _manual_records(log_json: str) -> dict[str, tuple[dict, Hlc]]:
    """Return ``{record_id: (payload, hlc)}`` for manual records in a log blob.

    Raises the same decode errors as :func:`_records_matching`; callers treat a
    corrupt device log as "no manual records from that device".
    """
    return _records_matching(log_json, _is_manual_payload)


def pull_all_manual_records() -> list[tuple[str, dict]]:
    """Return all synced manual-workout records across every device log.

    Merges every ``devices/<device>/log.json`` under the sync prefix (phone,
    pc, …), keeping the highest-HLC copy of each record id — records are
    id-stable, so the same workout mirrored into two device logs dedups to one.
    Best-effort: an unconfigured token, an unreachable repo, or a corrupt device
    log yields fewer/no records rather than raising — manual sync, like session
    sync, is optional.
    """
    client = sync_client()
    if client is None:
        return []

    merged = _merge_device_records(client, _manual_records, "manual workouts")
    return [(rid, payload) for rid, (payload, _hlc) in merged.items()]
