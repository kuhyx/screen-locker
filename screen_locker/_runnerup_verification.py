"""RunnerUp run auto-verification via ADB SQLite DB pull.

Pulls RunnerUp's private database directly from a rooted device, then
queries it locally.  No user interaction is required — the whole pipeline
runs in the background just like ``_phone_verification.py``.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
import time
from typing import Any

from screen_locker._constants import (
    MIN_RUN_DISTANCE_KM,
    MIN_RUN_DURATION_MINUTES,
    RUNNERUP_ACCEPTED_SPORTS,
    RUNNERUP_DB_SDCARD_TMP,
    RUNNERUP_PACKAGES,
)
from screen_locker._time_check import check_clock_skew

_logger = logging.getLogger(__name__)

_SPORT_NAMES: dict[int, str] = {
    0: "Running",
    1: "Biking",
    2: "Other",
    3: "Orienteering",
    4: "Walking",
    5: "Treadmill",
    6: "Gym",
    7: "Stationary Bike",
}


class RunnerUpVerificationMixin:
    """Mixin providing RunnerUp-based workout verification via ADB DB pull."""

    def _find_runnerup_package(self) -> str | None:
        """Return the first installed RunnerUp package name, or None."""
        for pkg in RUNNERUP_PACKAGES:
            ok, out = self._adb_shell(f"pm list packages {pkg}")
            if ok and pkg in out:
                return pkg
        return None

    def _pull_runnerup_db(self) -> str | None:
        """Pull RunnerUp's SQLite DB from the device to a local temp file.

        Copies the DB and any WAL/SHM sidecar files via root shell to
        ``/sdcard`` (accessible without root by adb pull), then pulls them
        locally.  WAL files must travel with the main DB so that
        ``PRAGMA wal_checkpoint`` can merge in-flight writes.

        Returns the local DB path on success, or ``None`` on any failure.
        """
        pkg = self._find_runnerup_package()
        if pkg is None:
            _logger.info("RunnerUp not installed (tried %s)", RUNNERUP_PACKAGES)
            return None

        db_device = f"/data/data/{pkg}/databases/runnerup.db"
        tmp_dir = tempfile.mkdtemp(prefix="runnerup_verify_")
        local_db = os.path.join(tmp_dir, "runnerup.db")

        # Copy the main DB to sdcard where adb pull can reach it (root needed).
        ok, err = self._adb_shell(
            f"cp {db_device} {RUNNERUP_DB_SDCARD_TMP}",
            root=True,
        )
        if not ok:
            _logger.info("Failed to copy RunnerUp DB to sdcard: %s", err)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        # Copy WAL and SHM sidecars if they exist; ignore failure (they may not).
        for suffix in ("-wal", "-shm"):
            self._adb_shell(
                f"test -f {db_device}{suffix} "
                f"&& cp {db_device}{suffix} {RUNNERUP_DB_SDCARD_TMP}{suffix} "
                f"|| true",
                root=True,
            )

        # Pull main DB.
        ok, _ = self._run_adb(["pull", RUNNERUP_DB_SDCARD_TMP, local_db])
        if not ok:
            _logger.info("adb pull of RunnerUp DB failed")
            self._cleanup_runnerup_sdcard()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        # Pull sidecars (best-effort; sqlite3 tolerates missing ones).
        for suffix in ("-wal", "-shm"):
            self._run_adb(
                ["pull", f"{RUNNERUP_DB_SDCARD_TMP}{suffix}", f"{local_db}{suffix}"]
            )

        self._cleanup_runnerup_sdcard()
        return local_db

    def _cleanup_runnerup_sdcard(self) -> None:
        """Remove temporary RunnerUp DB files from the sdcard."""
        for suffix in ("", "-wal", "-shm"):
            self._adb_shell(
                f"test -f {RUNNERUP_DB_SDCARD_TMP}{suffix} "
                f"&& rm {RUNNERUP_DB_SDCARD_TMP}{suffix} || true",
                root=True,
            )

    def _query_todays_run(self, db_path: str) -> dict[str, Any] | None:
        """Query the pulled RunnerUp DB for today's most recent activity.

        Runs ``PRAGMA wal_checkpoint`` first so that any uncommitted WAL
        entries are visible to the query (important for runs just finished).

        Returns a dict with ``distance_m``, ``duration_seconds``, and
        ``sport`` on success; ``None`` if no matching row exists.
        """
        # Build today's epoch window in local time (RunnerUp stores seconds).
        local_midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        local_end = local_midnight + 86400

        try:
            with sqlite3.connect(db_path, timeout=5) as conn:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                cursor = conn.execute(
                    """
                    SELECT start_time, distance, time, type
                    FROM activity
                    WHERE deleted = 0
                      AND start_time >= ?
                      AND start_time < ?
                    ORDER BY start_time DESC
                    LIMIT 1
                    """,
                    (local_midnight, local_end),
                )
                row = cursor.fetchone()
        except sqlite3.Error as exc:
            _logger.info("RunnerUp DB query failed: %s", exc)
            return None

        if row is None:
            return None

        start_time, distance_m, duration_seconds, sport = row
        return {
            "start_time": int(start_time or 0),
            "distance_m": float(distance_m or 0),
            "duration_seconds": int(duration_seconds or 0),
            "sport": int(sport or 0),
        }

    def _validate_runnerup_data(
        self, data: dict[str, Any]
    ) -> tuple[str, str]:
        """Validate a RunnerUp activity against configured thresholds.

        Returns ``(status, message)`` following the same contract as
        ``PhoneVerificationMixin._verify_phone_workout``.
        """
        sport = data["sport"]
        if sport not in RUNNERUP_ACCEPTED_SPORTS:
            sport_name = _SPORT_NAMES.get(sport, f"unknown({sport})")
            return (
                "wrong_sport",
                f"Activity type '{sport_name}' doesn't count as a qualifying run",
            )

        duration_min = data["duration_seconds"] / 60
        if duration_min < MIN_RUN_DURATION_MINUTES:
            return (
                "too_short",
                f"Run was {duration_min:.0f} min — need at least {MIN_RUN_DURATION_MINUTES} min",
            )

        distance_km = data["distance_m"] / 1000
        if distance_km < MIN_RUN_DISTANCE_KM:
            return (
                "too_short",
                f"Run was {distance_km:.1f} km — need at least {MIN_RUN_DISTANCE_KM:.0f} km",
            )

        sport_name = _SPORT_NAMES.get(sport, str(sport))
        return (
            "verified",
            f"{sport_name}: {distance_km:.1f} km in {duration_min:.0f} min",
        )

    def _verify_runnerup_workout(self) -> tuple[str, str]:
        """Verify today's run via RunnerUp DB pull.

        Entry point mirroring ``PhoneVerificationMixin._verify_phone_workout``.
        Status values: ``verified | not_verified | no_phone | too_short |
        wrong_sport | clock_tampered``.
        """
        skew_ok, skew_msg = check_clock_skew()
        if not skew_ok:
            return "clock_tampered", skew_msg

        if not self._has_adb_device():
            return (
                "no_phone",
                "Phone not connected — plug in via ADB to verify RunnerUp run",
            )

        db_path = self._pull_runnerup_db()
        if db_path is None:
            return "not_verified", "Could not retrieve RunnerUp database from phone"

        try:
            run_data = self._query_todays_run(db_path)
        finally:
            shutil.rmtree(os.path.dirname(db_path), ignore_errors=True)

        if run_data is None:
            return "not_verified", "No RunnerUp activity found for today"

        return self._validate_runnerup_data(run_data)
