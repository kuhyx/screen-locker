"""RunnerUp run auto-verification via ADB (file-based path + shared validation).

File-based (no root, works over WiFi): reads per-activity TCX files that
RunnerUp's File Synchronizer writes to ``/sdcard/Documents/RunnerUp/``.
Root DB fallback lives in ``_runnerup_db.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from screen_locker._constants import (
    MIN_RUN_DISTANCE_KM,
    RUNNERUP_DISTANCE_TOLERANCE,
    RUNNERUP_EXPORT_DIRS,
    RUNNERUP_WEBDAV_DIRS,
)
from screen_locker._day import today_str
from screen_locker._runnerup_backfill import RunnerUpBackfillMixin
from screen_locker._runnerup_db import RunnerUpDbMixin
from screen_locker._runnerup_tcx import RunnerUpTcxMixin
from screen_locker._time_check import check_clock_skew
from screen_locker._walk_tcx import (
    SPORT_NAMES,
    activity_day,
    activity_shortfall,
    distance_qualifies,
)

_logger = logging.getLogger(__name__)

# Kept for importers; the labels live next to the one crediting rule.
_SPORT_NAMES = SPORT_NAMES

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

    def _has_runnerup_source(self) -> bool:
        """Whether any RunnerUp export source is reachable right now.

        The WebDAV drop directory on this disk counts as much as an
        adb-visible phone: both hold the same TCX files.
        """
        return self._has_local_runnerup_dir() or self._has_adb_device()

    @staticmethod
    def _has_local_runnerup_dir() -> bool:
        return any(d.is_dir() for d in RUNNERUP_WEBDAV_DIRS)

    @staticmethod
    def _find_local_runnerup_exports_for_date(date_str: str) -> list[str]:
        """TCX files for ``date_str`` in the WebDAV drop directories, sorted."""
        found: list[str] = []
        for local_dir in RUNNERUP_WEBDAV_DIRS:
            if not local_dir.is_dir():
                continue
            for path in sorted(local_dir.glob("*.tcx")):
                if date_str in path.name and str(path) not in found:
                    found.append(str(path))
        return found

    def _find_runnerup_exports_for_date(self, date_str: str) -> list[str]:
        """Return paths of RunnerUp TCX exports for the given date, or empty list.

        Local WebDAV copies come first (no phone needed), then the phone's
        export directories over adb when a device is attached.

        Args:
            date_str: ISO date string in ``YYYY-MM-DD`` format matched against
                TCX filenames (``RunnerUp_YYYY-MM-DD-HH-MM-SS_xxx.tcx``).
        """
        found = self._find_local_runnerup_exports_for_date(date_str)
        if not self._has_adb_device():
            return found
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
        today = today_str()
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

        # One rule for the whole day, whatever the sport or file name: the
        # day's activities are summed (see _walk_tcx), never judged one file
        # at a time.
        activities = [
            data
            for remote in exports
            if (data := self._pull_and_parse_tcx(remote)) is not None
        ]
        if not activities:
            return (
                "not_verified",
                "RunnerUp TCX export found but could not be read",
            )
        day = activity_day(activities)
        if day.qualifies:
            return "verified", day.message()
        return "too_short", activity_shortfall(day)

    def _validate_runnerup_data(self, data: dict[str, Any]) -> tuple[str, str]:
        """Validate a RunnerUp activity against configured thresholds.

        Returns ``(status, message)`` following the same contract as
        ``PhoneVerificationMixin._verify_phone_workout``. The one rule is
        :func:`screen_locker._walk_tcx.activity_day`; a dict without
        ``moving_seconds`` (the root-DB path) is judged by its duration.
        """
        day = activity_day([data])
        if not day.qualifies:
            return "too_short", activity_shortfall(day)
        if day.distance_km < MIN_RUN_DISTANCE_KM and distance_qualifies(
            day.distance_km
        ):
            _logger.info(
                "RunnerUp distance %.2f km is under the %.1f km minimum but "
                "within %.0f%% GPS tolerance — accepted.",
                day.distance_km,
                MIN_RUN_DISTANCE_KM,
                RUNNERUP_DISTANCE_TOLERANCE * 100,
            )
        return "verified", day.message()

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

        if not self._has_runnerup_source():
            return (
                "no_phone",
                "Phone not connected — plug in via USB or enable wireless ADB",
            )

        # Path 1: file-based (no root needed; WebDAV copies first, then adb).
        file_result = self._verify_runnerup_via_files()
        if file_result is not None:
            _logger.info("RunnerUp file-based result: %s", file_result[0])
            return file_result

        # Path 2: root DB pull (fallback when no export files found yet).
        # On a non-rooted device this path cannot succeed; _verify_runnerup_via_db
        # reports that plainly rather than as a generic failure. Needs adb.
        if not self._has_adb_device():
            return (
                "not_verified",
                (
                    f"No RunnerUp export for today in {RUNNERUP_WEBDAV_DIRS} "
                    "and the phone is not adb-reachable"
                ),
            )
        return self._verify_runnerup_via_db()
