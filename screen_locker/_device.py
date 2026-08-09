"""This machine's persisted sync identity.

Its own module so both the manual-push writer (:mod:`screen_locker._manual_push`)
and the workout reader (:mod:`screen_locker._workout_sync`) can resolve the id
without importing each other.
"""

from __future__ import annotations

from crdt_sync import DeviceIdentity, load_device_identity

from screen_locker._constants import SYNC_DEVICE_ID_FILE, SYNC_LEGACY_DEVICE_ID


def device_identity() -> DeviceIdentity:
    """Return this machine's sync identity, minting it on first use.

    Deliberately not cached at import time: the id file is redirected
    per-test, and a module-level constant would freeze whichever value the
    first import happened to see.
    """
    return load_device_identity(SYNC_DEVICE_ID_FILE, legacy_id=SYNC_LEGACY_DEVICE_ID)
