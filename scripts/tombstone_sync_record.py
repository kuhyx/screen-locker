#!/usr/bin/env python3
"""Tombstone one workout record in the shared sync store, durably.

Deletion in crdt_sync is monotonic: once a device log carries ``deleted=True``
for an id, every merge keeps it deleted. But ``sync_log`` pulls only the OTHER
devices' logs and ``_manual_push`` re-derives the PC's log from ``log.json``
every tick, so a tombstone written once to the PC's device log is gone by the
next push (seen 2026-09-13: "tombstoned", then "LIVE" five seconds later).
So this records the id in ``screen_locker/sync_tombstones.json``
(``_sync_tombstones``), which every push carries, then runs one sync tick and
reports what the store holds afterwards.

Written for ``manual:2026-09-13T14:30``: a synced copy of a football already
on disk, filed under a second id by that morning's day-key repair. It shares
the original's credit (``_weekly_check.credit_key``) and stays in the signed
log -- this repo annotates, never deletes -- but its sync record made every
15-minute tick log "budget exhausted -- not ingested".

Dry-run by default: pulls the store and reports whether the id is live.
Rerunnable: an id already in the ledger is left as it is.

Usage:
    python3 scripts/tombstone_sync_record.py manual:2026-09-13T14:30
    python3 scripts/tombstone_sync_record.py manual:2026-09-13T14:30 --apply \
        --reason "synced duplicate of manual:2026-09-12T14:30"
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from crdt_sync import (
    FileSyncStateStore,
    GitHubSyncClient,
    LogCodec,
    Record,
    RevisionTracking,
    SyncTarget,
    sync_log,
)

from screen_locker._constants import (
    SYNC_REPO_NAME,
    SYNC_REPO_OWNER,
    SYNC_STATE_FILE,
    SYNC_TIMEOUT_SECONDS,
)
from screen_locker._device import device_identity
from screen_locker._manual_push import (
    _decode_log,
    _encode_log,
    records_from_workout_log,
)
from screen_locker._sync_tombstones import add_tombstone
from screen_locker._workout_sync import _DEVICES_PREFIX, read_sync_token, remote_client

_logger = logging.getLogger(__name__)

# The same path ScreenLocker resolves at runtime (screen_lock.py), as the
# sibling scripts do; there is no package constant for it.
LOG_FILE = Path(__file__).resolve().parent.parent / "screen_locker" / "log.json"


def _report(message: str) -> None:
    """Write one line to stdout (matches the other scripts in this directory)."""
    sys.stdout.write(f"{message}\n")


def _sync(local_log: dict[str, Record]) -> dict[str, Record]:
    """Run one sync tick with *local_log* as this device's view; return the merge."""
    identity = device_identity()
    token = read_sync_token()
    if token is None:
        msg = "no sync token — cannot reach the store"
        raise SystemExit(msg)
    client = remote_client(
        GitHubSyncClient(
            SYNC_REPO_OWNER, SYNC_REPO_NAME, token, timeout_seconds=SYNC_TIMEOUT_SECONDS
        )
    )
    return sync_log(
        SyncTarget(
            client=client,
            device_id=identity.device_id,
            legacy_device_id=identity.legacy_id,
            path_prefix=_DEVICES_PREFIX,
        ),
        local_log,
        LogCodec(decode=_decode_log, encode=_encode_log),
        RevisionTracking(state_store=FileSyncStateStore(SYNC_STATE_FILE)),
    )


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "record_id", help="sync record id, e.g. manual:2026-09-13T14:30"
    )
    parser.add_argument("--apply", action="store_true", help="write the tombstone")
    parser.add_argument("--reason", default="", help="why (kept in the ledger)")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.apply:
        if not args.reason:
            parser.error("--apply needs --reason so the ledger says why")
        if add_tombstone(args.record_id, device_identity().device_id, args.reason):
            _report(f"{args.record_id}: added to the tombstone ledger")
        else:
            _report(f"{args.record_id}: already in the tombstone ledger")
    # Exactly what _manual_push pushes on a tick: log.json plus the ledger.
    local_log = records_from_workout_log(LOG_FILE)
    merged = _sync(local_log)

    record = merged.get(args.record_id)
    if record is None:
        _report(
            f"{args.record_id}: not in the store on any device — nothing to tombstone"
        )
        return 1
    if record.deleted:
        verb = "tombstoned" if args.apply else "already tombstoned"
        _report(f"{args.record_id}: {verb} (deleted_hlc={record.deleted_hlc})")
        return 0
    _report(
        f"{args.record_id}: LIVE in the store — re-run with --apply to tombstone it"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
