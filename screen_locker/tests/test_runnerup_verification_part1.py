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

# TCX with an unrecognised sport tag (not in RUNNERUP_ACCEPTED_SPORTS).
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
# _validate_runnerup_data
# ---------------------------------------------------------------------------


class TestValidateRunnerupData:
    """Tests for _validate_runnerup_data (lines 388-411)."""

    def test_wrong_sport_returns_wrong_sport_status(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Sport not in RUNNERUP_ACCEPTED_SPORTS → wrong_sport."""
        locker = create_locker(mock_tk, tmp_path)
        # Sport 6 = Gym, not accepted
        status, msg = locker._validate_runnerup_data(
            {"sport": 6, "duration_seconds": 3600, "distance_m": 6000}
        )
        assert status == "wrong_sport"
        assert "Gym" in msg

    def test_unknown_sport_number_shown_in_message(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Unknown sport integer falls back to 'unknown(N)' label."""
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 99, "duration_seconds": 3600, "distance_m": 6000}
        )
        assert status == "wrong_sport"
        assert "unknown(99)" in msg

    def test_short_duration_alone_still_verified_on_distance(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Short duration alone is not enough to reject — distance still qualifies.

        The criteria are an OR, so 6 km in 1 min is verified on distance. If
        the OR ever regressed to an AND this would return too_short.
        """
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 60, "distance_m": 6000}
        )
        assert status == "verified"
        assert "6.0 km" in msg

    def test_too_short_distance_returns_too_short(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Both criteria missed → too_short naming both.

        0.1 km is far under the distance line and 30 min is under the duration
        line, so neither branch of the OR qualifies.
        """
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 1800, "distance_m": 100}
        )
        assert status == "too_short"
        assert "3.5+ km" in msg
        assert "40+ min" in msg

    def test_valid_run_returns_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Sufficient sport, duration, distance → verified with sport name in message."""
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 2400, "distance_m": 6000}
        )
        assert status == "verified"
        assert "Running" in msg

    def test_orienteering_accepted(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Sport 3 (Orienteering) is in RUNNERUP_ACCEPTED_SPORTS."""
        locker = create_locker(mock_tk, tmp_path)
        status, _ = locker._validate_runnerup_data(
            {"sport": 3, "duration_seconds": 2400, "distance_m": 6000}
        )
        assert status == "verified"


# ---------------------------------------------------------------------------
# _parse_tcx
# ---------------------------------------------------------------------------
