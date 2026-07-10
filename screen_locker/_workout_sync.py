"""Pulls the phone's last-synced workout via crdt-sync's GitHub transport.

GitHub is used purely as dumb file storage (see ``crdt_sync``'s own docs) --
the phone app pushes its completed-workout log to a private repo; this
module only ever reads it, it never pushes here itself (the PC has no
workout data of its own to contribute). Sync is optional: an unconfigured
token is a normal, expected state, not an error -- unlike diet_guard, where
sync is core to the app.
"""

from __future__ import annotations

import json
import logging

from crdt_sync import GitHubSyncClient, GitHubSyncError, Record

from screen_locker._constants import (
    SYNC_PHONE_DEVICE_ID,
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_TIMEOUT_SECONDS,
    SYNC_TOKEN_FILE,
)

_logger = logging.getLogger(__name__)

_LOG_PATH = f"screen-locker-sync/devices/{SYNC_PHONE_DEVICE_ID}/log.json"
_PAYLOAD_FIELD = "payload"


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
    candidates = [record for record in records if _PAYLOAD_FIELD in record.fields]
    if not candidates:
        return None
    latest = max(candidates, key=lambda record: record.fields[_PAYLOAD_FIELD][1])

    payload = latest.fields[_PAYLOAD_FIELD][0]
    if not isinstance(payload, dict):
        msg = f"payload field is not a JSON object: {payload!r}"
        raise TypeError(msg)
    return payload


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
        return None, None

    client = GitHubSyncClient(
        SYNC_REPO_OWNER,
        SYNC_REPO_NAME,
        token,
        timeout_seconds=SYNC_TIMEOUT_SECONDS,
    )
    try:
        text = client.get_file_text(_LOG_PATH)
    except GitHubSyncError as exc:
        return None, str(exc)

    if text is None:
        return None, None

    try:
        payload = _latest_payload(text)
    except (ValueError, KeyError, TypeError) as exc:
        _logger.warning("Corrupt sync data at %s: %s", _LOG_PATH, exc)
        return None, f"corrupt sync data: {exc}"

    return payload, None
