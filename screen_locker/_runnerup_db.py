"""Mixin: RunnerUp root-DB pull path (fallback when no TCX exports found)."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any

from screen_locker._constants import (
    RUNNERUP_DB_SDCARD_TMP,
    RUNNERUP_PACKAGES,
)

_logger = logging.getLogger(__name__)


class RunnerUpDbMixin:
    """Mixin: root DB pull for RunnerUp workout verification.

    Called as fallback when no TCX export files are found for today.
    Relies on _adb_shell, _run_adb, and _validate_runnerup_data from MRO.
    """

    def _find_runnerup_package(self) -> str | None:
        """Return the first installed RunnerUp package name, or None."""
        for pkg in RUNNERUP_PACKAGES:
            ok, out = self._adb_shell(f"pm list packages {pkg}")
            if ok and pkg in out:
                return pkg
        return None

    def _pull_runnerup_db(self) -> str | None:
        """Pull RunnerUp's SQLite DB from the device to a local temp file.

        Copies the DB and WAL/SHM sidecar files via root shell to ``/sdcard``
        (accessible without root by adb pull), then pulls them locally.
        WAL files must travel with the main DB so that ``PRAGMA wal_checkpoint``
        can merge in-flight writes.

        Returns the local DB path on success, or ``None`` on any failure.
        """
        pkg = self._find_runnerup_package()
        if pkg is None:
            _logger.info("RunnerUp not installed (tried %s)", RUNNERUP_PACKAGES)
            return None

        db_device = f"/data/data/{pkg}/databases/runnerup.db"
        tmp_dir = tempfile.mkdtemp(prefix="runnerup_verify_")
        local_db = str(Path(tmp_dir) / "runnerup.db")

        ok, err = self._adb_shell(
            f"cp {db_device} {RUNNERUP_DB_SDCARD_TMP}",
            root=True,
        )
        if not ok:
            _logger.info("Failed to copy RunnerUp DB to sdcard: %s", err)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        for suffix in ("-wal", "-shm"):
            self._adb_shell(
                f"test -f {db_device}{suffix} "
                f"&& cp {db_device}{suffix} {RUNNERUP_DB_SDCARD_TMP}{suffix} "
                f"|| true",
                root=True,
            )

        ok, _ = self._run_adb(["pull", RUNNERUP_DB_SDCARD_TMP, local_db])
        if not ok:
            _logger.info("adb pull of RunnerUp DB failed")
            self._cleanup_runnerup_sdcard()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

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

        Runs ``PRAGMA wal_checkpoint`` first so that uncommitted WAL entries
        are visible (important for runs just finished before connecting).
        """
        local_midnight = time.mktime((*time.localtime()[:3], 0, 0, 0, 0, 0, -1))
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
            _logger.warning(
                "RunnerUp activity query against %s failed: %s — treating it as "
                "no run recorded today",
                db_path,
                exc,
            )
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

    def _verify_runnerup_via_db(self) -> tuple[str, str]:
        """Verify today's run via root DB pull (fallback path)."""
        db_path = self._pull_runnerup_db()
        if db_path is None:
            return "not_verified", "Could not retrieve RunnerUp database from phone"

        try:
            run_data = self._query_todays_run(db_path)
        finally:
            shutil.rmtree(Path(db_path).parent, ignore_errors=True)

        if run_data is None:
            return "not_verified", "No RunnerUp activity found for today"

        return self._validate_runnerup_data(run_data)
