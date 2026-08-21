"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

# Minimal valid TCX XML for a 40-minute, 6-km run.
_TCX_RUNNING = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap>
        <TotalTimeSeconds>2400.0</TotalTimeSeconds>
        <DistanceMeters>6000.0</DistanceMeters>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""

# TCX with a non-running sport tag (Gym).
_TCX_GYM = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Gym">
      <Lap>
        <TotalTimeSeconds>3600.0</TotalTimeSeconds>
        <DistanceMeters>0.0</DistanceMeters>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""

# Two laps that together make a valid run.
_TCX_MULTI_LAP = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap>
        <TotalTimeSeconds>1200.0</TotalTimeSeconds>
        <DistanceMeters>3000.0</DistanceMeters>
      </Lap>
      <Lap>
        <TotalTimeSeconds>1200.0</TotalTimeSeconds>
        <DistanceMeters>3000.0</DistanceMeters>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tcx(tmp_path: Path, content: str, name: str = "activity.tcx") -> str:
    """Write TCX content to a temp file and return the path string."""
    p = tmp_path / name
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# _validate_runnerup_data — GPS distance tolerance
# ---------------------------------------------------------------------------


class TestValidateRunnerupDataDistanceTolerance:
    """A run just under MIN_RUN_DISTANCE_KM is accepted within 5% GPS tolerance."""

    def test_distance_within_tolerance_is_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """3.45 km * 1.05 = 3.62 >= 3.5 km minimum → verified.

        Duration is held under 40 min so the distance branch is what is
        actually under test, not the duration branch of the OR.
        """
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 1500, "distance_m": 3450.0}
        )
        assert status == "verified"
        assert "3.5 km" in msg

    def test_distance_below_tolerance_is_too_short(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """3.0 km * 1.05 = 3.15 km, still short of the 3.5 km minimum → too_short.

        Duration is under 40 min so the duration branch cannot rescue it.
        """
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 1500, "distance_m": 3000}
        )
        assert status == "too_short"
        assert "3.5+ km" in msg

    def test_distance_at_full_minimum_is_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A run already meeting the minimum outright still passes (tolerance is
        additive leeway, not a stricter requirement)."""
        locker = create_locker(mock_tk, tmp_path)
        status, _ = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 1947, "distance_m": 5000}
        )
        assert status == "verified"
