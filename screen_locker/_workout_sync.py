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

from crdt_sync import (
    CONFIG_FILE,
    ConfigError,
    FirebaseAuthError,
    GitHubSyncClient,
    GitHubSyncError,
    Hlc,
    Record,
    RemoteStore,
    RemoteSyncError,
    mirror_client_for,
)

from screen_locker._constants import (
    SYNC_PHONE_DEVICE_ID,
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TIMEOUT_SECONDS,
    SYNC_TOKEN_FILE,
)
from screen_locker._manual_workout import MANUAL_WORKOUT_SYNC_KIND
from screen_locker._sync_retry import with_sync_retry

_logger = logging.getLogger(__name__)

_DEVICES_PREFIX = "screen-locker-sync/devices"
_LOG_PATH = f"{_DEVICES_PREFIX}/{SYNC_PHONE_DEVICE_ID}/log.json"
_PAYLOAD_FIELD = "payload"


def _is_manual_payload(payload: object) -> bool:
    """True if a decoded sync payload is a manual-workout record."""
    return isinstance(payload, dict) and payload.get("kind") == MANUAL_WORKOUT_SYNC_KIND


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


def _latest_payload(log_json: str) -> dict | None:
    """Return the most recently pushed workout payload from a log.json blob.

    Raises:
        TypeError: If the top-level JSON isn't an object, a record's shape
            doesn't match what :meth:`Record.from_dict` expects, or the
            payload field itself isn't a JSON object.
        KeyError: If a record is missing an expected key.
        ValueError: Via ``json.loads``, if the text isn't valid JSON, or via
            :meth:`crdt_sync.Hlc.from_str` on a malformed clock string.
    """
    raw = json.loads(log_json)
    if not isinstance(raw, dict):
        msg = f"top-level sync payload is not a JSON object: {raw!r}"
        raise TypeError(msg)

    records = [Record.from_dict(data) for data in raw.values()]
    candidates = [
        record
        for record in records
        if _PAYLOAD_FIELD in record.fields
        and not _is_manual_payload(record.fields[_PAYLOAD_FIELD][0])
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda record: record.fields[_PAYLOAD_FIELD][1])

    payload = latest.fields[_PAYLOAD_FIELD][0]
    if not isinstance(payload, dict):
        msg = f"payload field is not a JSON object: {payload!r}"
        raise TypeError(msg)
    return payload


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


def pull_synced_workout() -> tuple[dict | None, str | None]:
    """Return ``(data, error)``: the phone's last-synced workout, if any.

    - No token configured: ``(None, None)`` -- benign, sync is optional.
    - Nothing pushed yet (repo reachable, path unused): ``(None, None)``.
    - A real sync error (network, bad token, repo unreachable):
      ``(None, <message>)``.
    - Corrupt/malformed sync data: ``(None, "corrupt sync data: ...")``.
    - Success: ``(payload_dict, None)``.
    """
    token = read_sync_token()
    if token is None:
        _logger.warning(
            "Cannot pull the synced StrongLifts session: no sync token at %s — "
            "GitHub sync is OFF, so only ADB/HTTP can verify a phone workout. "
            "Create a fine-grained PAT with contents:write on %s/%s and save it "
            "there (chmod 600)",
            SYNC_TOKEN_FILE,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
        )
        return None, None

    client = remote_client(
        GitHubSyncClient(
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
            token,
            timeout_seconds=SYNC_TIMEOUT_SECONDS,
        )
    )
    try:
        text = with_sync_retry(
            lambda: client.get_file_text(_LOG_PATH),
            description="fetch the phone's workout log",
        )
    except GitHubSyncError as exc:
        _logger.warning(
            "Could not fetch the phone's workout log %s from %s/%s: %s — "
            "falling back to ADB/HTTP verification",
            _LOG_PATH,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
            exc,
        )
        return None, str(exc)

    if text is None:
        return None, None

    try:
        payload = _latest_payload(text)
    except (ValueError, KeyError, TypeError) as exc:
        _logger.warning("Corrupt sync data at %s: %s", _LOG_PATH, exc)
        return None, f"corrupt sync data: {exc}"

    return payload, None


def _manual_records(log_json: str) -> dict[str, tuple[dict, Hlc]]:
    """Return ``{record_id: (payload, hlc)}`` for manual records in a log blob.

    Raises the same decode errors as :func:`_latest_payload`; callers treat a
    corrupt device log as "no manual records from that device".
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
        if _is_manual_payload(payload):
            result[record.id] = (payload, hlc)
    return result


def pull_all_manual_records() -> list[tuple[str, dict]]:
    """Return all synced manual-workout records across every device log.

    Merges every ``devices/<device>/log.json`` under the sync prefix (phone,
    pc, …), keeping the highest-HLC copy of each record id — records are
    id-stable, so the same workout mirrored into two device logs dedups to one.
    Best-effort: an unconfigured token, an unreachable repo, or a corrupt device
    log yields fewer/no records rather than raising — manual sync, like session
    sync, is optional.
    """
    token = read_sync_token()
    if token is None:
        _logger.warning(
            "Pulling NO synced manual workouts: no sync token at %s — GitHub "
            "sync is OFF, so workouts logged on the phone will NOT count here. "
            "Create a fine-grained PAT with contents:write on %s/%s and save it "
            "there (chmod 600)",
            SYNC_TOKEN_FILE,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
        )
        return []

    client = remote_client(
        GitHubSyncClient(
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
            token,
            timeout_seconds=SYNC_TIMEOUT_SECONDS,
        )
    )
    try:
        devices = with_sync_retry(
            lambda: client.list_directory(_DEVICES_PREFIX),
            description="list synced device logs",
        )
    except GitHubSyncError as exc:
        _logger.warning(
            "Could not list device logs under %s in %s/%s: %s — pulling NO "
            "synced manual workouts, so phone-logged workouts will not count",
            _DEVICES_PREFIX,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
            exc,
        )
        return []

    merged: dict[str, tuple[dict, Hlc]] = {}
    for device in devices:
        path = f"{_DEVICES_PREFIX}/{device}/log.json"
        try:
            text = client.get_file_text(path)
        except GitHubSyncError as exc:
            _logger.warning(
                "Could not fetch device log %s: %s — SKIPPING that device, so "
                "any manual workouts it holds will not count",
                path,
                exc,
            )
            continue
        if text is None:
            continue
        try:
            records = _manual_records(text)
        except (ValueError, KeyError, TypeError) as exc:
            _logger.warning("Corrupt sync data at %s: %s", path, exc)
            continue
        for rid, (payload, hlc) in records.items():
            existing = merged.get(rid)
            if existing is None or existing[1] < hlc:
                merged[rid] = (payload, hlc)

    return [(rid, payload) for rid, (payload, _hlc) in merged.items()]
