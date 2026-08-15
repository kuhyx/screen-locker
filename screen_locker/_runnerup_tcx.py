"""Pulling a RunnerUp TCX export off the phone and parsing it.

Split out of :mod:`screen_locker._runnerup_verification` to keep every file
under the 250-line cap. Composed back into ``RunnerUpVerificationMixin``
there, so callers see no change.

TCX is the no-root path: RunnerUp writes these exports to shared storage, so
they can be read without touching the app's private database.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import tempfile
from typing import Any
import xml.etree.ElementTree as ET

# TCX XML namespace used by Garmin/RunnerUp.
_TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"

_SPORT_NAMES: dict[int, str] = {
    0: "Running",
    1: "Cycling",
    2: "Other",
    3: "Orienteering",
    4: "Walking",
    5: "Skiing",
    6: "Swimming",
    7: "Stationary Bike",
}

# TCX uses sport name strings; map back to integer codes for unified validation.
_TCX_SPORT_TO_INT: dict[str, int] = {v: k for k, v in _SPORT_NAMES.items()}

_logger = logging.getLogger(__name__)


class RunnerUpTcxMixin:
    """Pulls and parses RunnerUp's TCX exports over adb."""

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
