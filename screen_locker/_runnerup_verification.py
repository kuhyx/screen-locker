"""RunnerUp run auto-verification via ADB (file-based path + shared validation).

File-based (no root, works over WiFi): reads per-activity TCX files that
RunnerUp's File Synchronizer writes to ``/sdcard/Documents/RunnerUp/``.
Root DB fallback lives in ``_runnerup_db.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from screen_locker._constants import (
    MIN_RUN_DISTANCE_KM,
    MIN_WORKOUT_DURATION_MINUTES,
    RUNNERUP_DISTANCE_TOLERANCE,
    RUNNERUP_EXPORT_DIRS,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)
from screen_locker._runnerup_backfill import RunnerUpBackfillMixin
from screen_locker._runnerup_db import RunnerUpDbMixin
from screen_locker._runnerup_tcx import RunnerUpTcxMixin
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


class RunnerUpVerificationMixin(
    RunnerUpDbMixin,
    RunnerUpTcxMixin,
    RunnerUpBackfillMixin,
):
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

    def _verify_runnerup_via_files(self) -> tuple[str, str] | None:
        """Try to verify today's run via TCX export files.

        Returns ``(status, message)`` if a today's file was found (even if it
        fails validation), or ``None`` if no today's file exists at all
        (caller should try the root DB path instead).
        """
        today = datetime.now(tz=timezone.utc).astimezone().strftime("%Y-%m-%d")
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

    def _validate_runnerup_data(self, data: dict[str, Any]) -> tuple[str, str]:
        """Validate a RunnerUp activity against configured thresholds.

        Returns ``(status, message)`` following the same contract as
        ``PhoneVerificationMixin._verify_phone_workout``.
        """
        sport = data["sport"]

        duration_min = data["duration_seconds"] / 60
        distance_km = data["distance_m"] / 1000

        # Either criterion qualifies the run on its own (see _constants.py).
        # Distance gets the GPS tolerance (a measurement correction); duration
        # gets the shared hidden leeway (a deliberate concession). Different
        # reasons, so they stay separate constants.
        distance_ok = (
            distance_km * (1 + RUNNERUP_DISTANCE_TOLERANCE) >= MIN_RUN_DISTANCE_KM
        )
        duration_ok = duration_min >= WORKOUT_DURATION_ACCEPT_MINUTES
        if not distance_ok and not duration_ok:
            msg = (
                f"Run was {distance_km:.1f} km / {duration_min:.0f} min — need "
                f"{MIN_RUN_DISTANCE_KM:g}+ km or {MIN_WORKOUT_DURATION_MINUTES}+ min"
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
        clock_tampered``.
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
