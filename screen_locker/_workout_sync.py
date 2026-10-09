"""Pulls phone/other-device workouts via crdt-sync's Firebase transport.

Firebase RTDB is the only backend since 2026-10-09 (the old GitHub repo is a
frozen archive nobody reads) -- the phone app pushes its completed-workout log
there; this module
reads the session log and every device's manual-workout records. (The PC does
push its OWN manual workouts, but via :mod:`screen_locker._manual_push`, not
here.) Sync is optional: a machine without a Firebase config still locks
and verifies over ADB/HTTP -- but it says so at ``warning`` every time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from crdt_sync import (
    CONFIG_FILE,
    Hlc,
    RemoteStore,
    RemoteSyncError,
)

from screen_locker._sync_client import sync_client, sync_client_or_reason
from screen_locker._sync_records import (
    _is_manual_payload,
    _is_session_payload,
    _manual_records,
    _records_matching,
    _session_records,
    merge_device_texts,
)
from screen_locker._sync_retry import with_sync_retry

# Re-exported for callers (_manual_push, scripts/tombstone_sync_record.py).
__all__ = [
    "CONFIG_FILE",
    "_is_manual_payload",
    "_is_session_payload",
    "_manual_records",
    "_records_matching",
    "_session_records",
    "pull_all_manual_records",
    "pull_all_session_records",
    "pull_synced_workout",
    "sync_client",
    "sync_client_or_reason",
]

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_DEVICES_PREFIX = "screen-locker-sync/devices"
_PAYLOAD_FIELD = "payload"


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
            "Could not list device logs under %s in Firebase: %s — pulling NO "
            "synced %s, so phone-logged workouts will not count",
            _DEVICES_PREFIX,
            exc,
            what,
        )
        if strict:
            raise
        return {}

    texts: list[tuple[str, str]] = []
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
        if text is not None:
            texts.append((path, text))
    return merge_device_texts(texts, extract, what)


def pull_synced_workout() -> tuple[dict | None, str | None]:
    """Return ``(data, error)``: the last-synced StrongLifts session, if any.

    Merges sessions across EVERY device directory and returns the highest-HLC
    one. It used to read a single hardcoded ``devices/phone/log.json``, which
    silently went stale the moment the phone moved to a per-install uuid
    (ffc6c72): this machine kept happily returning a session from 2026-07-27
    while newer ones sat unread one directory over.

    - Nothing configured anywhere: ``(None, None)`` -- benign, sync is optional.
    - Nothing pushed yet: ``(None, None)``.
    - A real sync error (network, rejected credential, backend unreachable):
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


def pull_all_session_records() -> list[tuple[str, dict]]:
    """Return all synced StrongLifts sessions across every device log.

    The session counterpart to :func:`pull_all_manual_records`, and the reason
    a workout finished on the PC reaches ``log.json`` without a lock screen
    being open: ``pull_synced_workout`` returns only the single newest session
    for the live unlock check, which cannot backfill a week.

    Best-effort in the same way -- no Firebase config or a corrupt device
    log yields fewer records rather than raising.
    """
    client = sync_client()
    if client is None:
        _logger.warning(
            "No usable Firebase sync client (see the warning above) — "
            "synced StrongLifts sessions cannot be pulled, so a workout done "
            "on another device will NOT count toward the weekly minimum.",
        )
        return []

    merged = _merge_device_records(client, _session_records, "sessions")
    return [(rid, payload) for rid, (payload, _hlc) in merged.items()]


def pull_all_manual_records() -> list[tuple[str, dict]]:
    """Return all synced manual-workout records across every device log.

    Merges every ``devices/<device>/log.json`` under the sync prefix (phone,
    pc, …), keeping the highest-HLC copy of each record id — records are
    id-stable, so the same workout mirrored into two device logs dedups to one.
    Best-effort: no Firebase config, an unreachable store, or a corrupt device
    log yields fewer/no records rather than raising — manual sync, like session
    sync, is optional.
    """
    client = sync_client()
    if client is None:
        return []

    merged = _merge_device_records(client, _manual_records, "manual workouts")
    return [(rid, payload) for rid, (payload, _hlc) in merged.items()]
