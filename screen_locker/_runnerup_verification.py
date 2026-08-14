"""RunnerUp run auto-verification via ADB (file-based path + shared validation).

File-based (no root, works over WiFi): reads per-activity TCX files that
RunnerUp's File Synchronizer writes to ``/sdcard/Documents/RunnerUp/``.
Root DB fallback lives in ``_runnerup_db.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
import tempfile
from typing import Any
import xml.etree.ElementTree as ET

from screen_locker._constants import (
    MIN_RUN_DISTANCE_KM,
    MIN_RUN_DURATION_MINUTES,
    RUNNERUP_ACCEPTED_SPORTS,
    RUNNERUP_DISTANCE_TOLERANCE,
    RUNNERUP_EXPORT_DIRS,
)
from screen_locker._log_mixin import write_signed_entry
from screen_locker._runnerup_db import RunnerUpDbMixin
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


class RunnerUpVerificationMixin(RunnerUpDbMixin):
    """Mixin providing RunnerUp-based workout verification via ADB."""

    # ------------------------------------------------------------------
    # File-based path (no root required)
    # ------------------------------------------------------------------

    def _find_runnerup_exports_for_date(self, date_str: str) -> list[str]:
        """Return adb paths of RunnerUp TCX exports for the given date, or empty list.

        Args:
            date_str: ISO date string in ``YYYY-MM-DD`` format matched against
                TCX filenames (``RunnerUp_YYYY-MM-DD-HH-MM-SS_xxx.tcx``).
        """
        found: list[str] = []
        for dirpath in RUNNERUP_EXPORT_DIRS:
            ok, out = self._run_adb(["shell", "ls", dirpath])
            if not ok or not out.strip():
                continue
            for raw in out.strip().splitlines():
                name = raw.strip()
                if date_str in name and name.endswith(".tcx"):
                    remote = f"{dirpath}/{name}"
                    if remote not in found:
                        found.append(remote)
        return found

    def _pull_and_parse_tcx(self, remote_path: str) -> dict[str, Any] | None:
        """Pull a remote TCX file and parse it. Returns activity dict or None."""
        tmp_dir = tempfile.mkdtemp(prefix="runnerup_tcx_")
        local_path = str(Path(tmp_dir) / "activity.tcx")
        try:
            ok, _ = self._run_adb(["pull", remote_path, local_path])
            if not ok or not Path(local_path).exists():
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
            tree = ET.parse(tcx_path)
        except ET.ParseError as exc:
            _logger.warning(
                "TCX file %s is not valid XML (%s) — the run it describes CANNOT "
                "be verified and will not count",
                tcx_path,
                exc,
            )
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
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        exports = self._find_runnerup_exports_for_date(today)
        if not exports:
            _logger.warning(
                "No RunnerUp TCX export found for %s in %s — a run today will "
                "not be verified unless RunnerUp's File Synchronizer "
                "auto-export is enabled and the app stays enabled long enough "
                "to sync (check it isn't disabled by focus mode).",
                today,
                RUNNERUP_EXPORT_DIRS,
            )
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
        return best or (
            "not_verified",
            "RunnerUp TCX export found but could not be read",
        )

    def _try_fill_runnerup_for_date(self, date_str: str, log_file: Path) -> bool:
        """Append a verified RunnerUp entry for ``date_str`` if not already logged.

        Appends via the write chokepoint, which dedups by ``workout_id``
        (``runnerup_verified:{date}``): re-scanning a day whose run is already
        recorded is a no-op, but a day that only holds, say, a manual workout
        still gets the run appended alongside it (multiple workouts per day).

        Returns True if a new verified entry was appended for ``date_str``.
        """
        for remote in self._find_runnerup_exports_for_date(date_str):
            data = self._pull_and_parse_tcx(remote)
            if data is None:
                continue
            status, msg = self._validate_runnerup_data(data)
            if status != "verified":
                _logger.warning(
                    "RunnerUp export %s for %s did not qualify (%s): %s",
                    remote,
                    date_str,
                    status,
                    msg,
                )
                continue
            workout_data = {
                "type": "runnerup_verified",
                "source": f"Auto-scanned: {msg}",
                "distance_km": round(data["distance_m"] / 1000, 2),
                "duration_minutes": round(data["duration_seconds"] / 60, 1),
            }
            if write_signed_entry(log_file, date_str, workout_data).appended:
                _logger.info("Auto-filled RunnerUp entry for %s: %s", date_str, msg)
                return True
            return False
        return False

    def _scan_and_fill_week_runnerup(self, log_file: Path) -> int:
        """Scan the current ISO week for RunnerUp runs and append any not logged.

        Returns the count of newly appended entries (0 if phone not connected).
        """
        if not self._has_adb_device():
            _logger.info(
                "Phone not connected; skipping auto-scan for past RunnerUp exports."
            )
            return 0

        now = datetime.now(tz=timezone.utc).astimezone()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())

        filled = 0
        current = week_start
        while current <= today:
            if self._try_fill_runnerup_for_date(current.strftime("%Y-%m-%d"), log_file):
                filled += 1
            current += timedelta(days=1)

        return filled

    # ------------------------------------------------------------------
    # Shared validation
    # ------------------------------------------------------------------

    def _validate_runnerup_data(self, data: dict[str, Any]) -> tuple[str, str]:
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
        distance_km = data["distance_m"] / 1000

        # Either criterion qualifies the run on its own (see _constants.py).
        # Distance gets the GPS tolerance; duration, from the device clock,
        # does not.
        distance_ok = (
            distance_km * (1 + RUNNERUP_DISTANCE_TOLERANCE) >= MIN_RUN_DISTANCE_KM
        )
        duration_ok = duration_min > MIN_RUN_DURATION_MINUTES
        if not distance_ok and not duration_ok:
            msg = (
                f"Run was {distance_km:.1f} km / {duration_min:.0f} min — need "
                f"{MIN_RUN_DISTANCE_KM:g}+ km or {MIN_RUN_DURATION_MINUTES}+ min"
            )
            return "too_short", msg
        if distance_ok and distance_km < MIN_RUN_DISTANCE_KM:
            _logger.info(
                "RunnerUp distance %.2f km is under the %.1f km minimum but "
                "within %.0f%% GPS tolerance — accepted.",
                distance_km,
                MIN_RUN_DISTANCE_KM,
                RUNNERUP_DISTANCE_TOLERANCE * 100,
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
        # On a non-rooted device this path cannot succeed; _verify_runnerup_via_db
        # reports that plainly rather than as a generic failure.
        return self._verify_runnerup_via_db()
