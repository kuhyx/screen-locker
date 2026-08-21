"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker._constants import (
    MIN_WORKOUT_DURATION_MINUTES,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)
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


class TestValidateRunnerupDataOrCriteria:
    """Distance and duration are an OR: either one alone qualifies a run."""

    def test_long_but_short_distance_is_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """2 km in 45 min → verified on the duration branch alone."""
        locker = create_locker(mock_tk, tmp_path)
        status, _ = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 2700, "distance_m": 2000}
        )
        assert status == "verified"

    def test_far_but_quick_is_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """3.6 km in 20 min → verified on the distance branch alone.

        The old rule imposed a 30-minute floor on every run; it is gone, so a
        fast run is no longer rejected for being quick.
        """
        locker = create_locker(mock_tk, tmp_path)
        status, _ = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 1200, "distance_m": 3600}
        )
        assert status == "verified"

    def test_neither_criterion_met_is_too_short(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """3.0 km in 25 min misses both branches; message names both."""
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 1500, "distance_m": 3000}
        )
        assert status == "too_short"
        # Pinned literally: a ':.0f' format spec would render 3.5 as "4".
        assert "need 3.5+ km or 40+ min" in msg

    def test_distance_boundary_is_inclusive(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Exactly 3.5 km qualifies ("as low as 3.5 km")."""
        locker = create_locker(mock_tk, tmp_path)
        status, _ = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 600, "distance_m": 3500}
        )
        assert status == "verified"

    def test_duration_boundary_uses_the_hidden_leeway(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Runs answer to the shared accept bar (35), not the advertised 40.

        The distance stays at 1 km throughout so the OR distance arm cannot
        rescue the run — this pins the duration arm alone.
        """
        locker = create_locker(mock_tk, tmp_path)
        just_under, _ = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 2094, "distance_m": 1000}
        )
        assert just_under == "too_short"
        at_accept_bar, _ = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 2100, "distance_m": 1000}
        )
        assert at_accept_bar == "verified"

    def test_too_short_message_advertises_40_not_the_real_cutoff(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """The hidden accept bar must never reach the user's eyes."""
        locker = create_locker(mock_tk, tmp_path)
        _, message = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 600, "distance_m": 1000}
        )
        assert str(MIN_WORKOUT_DURATION_MINUTES) in message
        assert str(WORKOUT_DURATION_ACCEPT_MINUTES) not in message

    def test_real_2026_08_14_run_is_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Regression: the real run this rule change was made for.

        Pulled from RunnerUp_2026-08-14-00-58-45_Running.tcx — 4 laps summing
        to 3817 m / 2502 s. It qualifies on both branches; under the previous
        AND rule it was rejected with "Run was 3.8 km — need 5+ km".
        """
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 2502, "distance_m": 3817.0}
        )
        assert status == "verified"
        assert "3.8 km" in msg


# ---------------------------------------------------------------------------
# _validate_runnerup_data
# ---------------------------------------------------------------------------
