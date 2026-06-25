"""RunnerUp run auto-verification via ADB.

Two verification paths, tried in order:

1. **File-based** (no root, works over WiFi): reads per-activity TCX files
   that RunnerUp's File Synchronizer writes to ``/sdcard/Documents/RunnerUp/``
   after each run.  Requires one-time setup in RunnerUp:
   Settings → Accounts → Add → File → format=TCX, dir=Documents/RunnerUp.

2. **Root DB pull** (fallback): copies RunnerUp's private SQLite database to
   sdcard via ``su``, pulls it locally, and queries it directly.  Used when
   no today's TCX export is found (e.g. sync hasn't fired yet, or File
   Synchronizer isn't configured).
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from screen_locker._constants import (
    MIN_RUN_DISTANCE_KM,
    MIN_RUN_DURATION_MINUTES,
    RUNNERUP_ACCEPTED_SPORTS,
    RUNNERUP_DB_SDCARD_TMP,
    RUNNERUP_EXPORT_DIRS,
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

# TCX uses sport name strings; map back to integer codes for unified validation.
_TCX_SPORT_TO_INT: dict[str, int] = {v: k for k, v in _SPORT_NAMES.items()}

# TCX XML namespace used by Garmin/RunnerUp.
_TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"


class RunnerUpVerificationMixin:
    """Mixin providing RunnerUp-based workout verification via ADB."""

    # ------------------------------------------------------------------
    # File-based path (no root required)
    # ------------------------------------------------------------------

    def _find_todays_runnerup_exports(self) -> list[str]:
        """Return adb paths of today's RunnerUp TCX exports, or empty list."""
        today = datetime.now().strftime("%Y-%m-%d")
        found: list[str] = []
        for dirpath in RUNNERUP_EXPORT_DIRS:
            ok, out = self._run_adb(["shell", "ls", dirpath])
            if not ok or not out.strip():
                continue
            for name in out.strip().splitlines():
                name = name.strip()
                if today in name and name.endswith(".tcx"):
                    remote = f"{dirpath}/{name}"
                    if remote not in found:
                        found.append(remote)
        return found

    def _pull_and_parse_tcx(self, remote_path: str) -> dict[str, Any] | None:
        """Pull a remote TCX file and parse it. Returns activity dict or None."""
        tmp_dir = tempfile.mkdtemp(prefix="runnerup_tcx_")
        local_path = os.path.join(tmp_dir, "activity.tcx")
        try:
            ok, _ = self._run_adb(["pull", remote_path, local_path])
            if not ok or not os.path.exists(local_path):
                _logger.info("Failed to pull TCX file: %s", remote_path)
                return None
            return self._parse_tcx(local_path)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _parse_tcx(self, tcx_path: str) -> dict[str, Any] | None:
        """Parse a local TCX file and return activity summary dict.

        Sums ``TotalTimeSeconds`` and ``DistanceMeters`` across all Laps so
        multi-segment runs (pause/resume) are counted in full.
        """
        try:
            tree = ET.parse(tcx_path)  # noqa: S314 — local file we pulled
        except ET.ParseError as exc:
            _logger.info("TCX parse error in %s: %s", tcx_path, exc)
            return None

        root = tree.getroot()
        activity = root.find(f".//{{{_TCX_NS}}}Activity")
        if activity is None:
            _logger.info("No Activity element in TCX file")
            return None

        sport_str = activity.get("Sport", "")
        sport_int = _TCX_SPORT_TO_INT.get(sport_str, -1)

        total_seconds = 0.0
        total_distance = 0.0
        for lap in activity.findall(f"{{{_TCX_NS}}}Lap"):
            t_elem = lap.find(f"{{{_TCX_NS}}}TotalTimeSeconds")
            d_elem = lap.find(f"{{{_TCX_NS}}}DistanceMeters")
            if t_elem is not None and t_elem.text:
                total_seconds += float(t_elem.text)
            if d_elem is not None and d_elem.text:
                total_distance += float(d_elem.text)

        return {
            "sport": sport_int,
            "duration_seconds": int(total_seconds),
            "distance_m": total_distance,
        }

    def _verify_runnerup_via_files(self) -> tuple[str, str] | None:
        """Try to verify today's run via TCX export files.

        Returns ``(status, message)`` if a today's file was found (even if it
        fails validation), or ``None`` if no today's file exists at all
        (caller should try the root DB path instead).
        """
        exports = self._find_todays_runnerup_exports()
        if not exports:
            return None

        # Try each file; return the best result (verified > validation error).
        best: tuple[str, str] | None = None
        for remote in exports:
            data = self._pull_and_parse_tcx(remote)
            if data is None:
                continue
            status, msg = self._validate_runnerup_data(data)
            if status == "verified":
                return status, msg
            if best is None:
                best = (status, msg)

        # All files found but none passed validation.
        return best or ("not_verified", "RunnerUp TCX export found but could not be read")

    # ------------------------------------------------------------------
    # Root DB pull path (fallback)
    # ------------------------------------------------------------------

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
        local_db = os.path.join(tmp_dir, "runnerup.db")

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

    def _verify_runnerup_via_db(self) -> tuple[str, str]:
        """Verify today's run via root DB pull (fallback path)."""
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

    # ------------------------------------------------------------------
    # Shared validation
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def _verify_runnerup_workout(self) -> tuple[str, str]:
        """Verify today's run via RunnerUp.

        Tries TCX file exports first (no root, works over WiFi); falls back to
        root DB pull if no today's files are found.

        Status values: ``verified | not_verified | no_phone | too_short |
        wrong_sport | clock_tampered``.
        """
        skew_ok, skew_msg = check_clock_skew()
        if not skew_ok:
            return "clock_tampered", skew_msg

        if not self._has_adb_device():
            return (
                "no_phone",
                "Phone not connected — plug in via USB or enable wireless ADB",
            )

        # Path 1: file-based (no root needed).
        file_result = self._verify_runnerup_via_files()
        if file_result is not None:
            _logger.info("RunnerUp file-based result: %s", file_result[0])
            return file_result

        # Path 2: root DB pull (fallback when no export files found yet).
        _logger.info("No TCX exports found today; trying root DB pull...")
        return self._verify_runnerup_via_db()
