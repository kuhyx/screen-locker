"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker._constants import (
    MIN_WORKOUT_DURATION_MINUTES,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

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


class TestVerifyRunnerupViaFiles:
    """Tests for _verify_runnerup_via_files (lines 147-165)."""

    def test_returns_none_when_no_exports_found(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No exports for today → None (caller tries DB path)."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=[]),
        )
        assert locker._verify_runnerup_via_files() is None

    def test_returns_verified_when_file_passes(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """First valid file → verified immediately."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/run.tcx"]),
        )
        object.__setattr__(
            locker,
            "_pull_and_parse_tcx",
            MagicMock(
                return_value={"sport": 0, "duration_seconds": 2400, "distance_m": 6000}
            ),
        )
        status, _ = locker._verify_runnerup_via_files()
        assert status == "verified"

    def test_returns_best_when_no_file_verified(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Files found but none verified → returns first non-None validation result.

        Both duration and distance are held under their minimums so the OR
        in _validate_runnerup_data cannot rescue this fixture on either
        branch — otherwise a fixture qualifying on one branch alone would
        turn this into a test of that branch, not of the "no file verified"
        return-first-result behavior this test is actually about.
        """
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/run.tcx"]),
        )
        object.__setattr__(
            locker,
            "_pull_and_parse_tcx",
            MagicMock(
                return_value={"sport": 0, "duration_seconds": 60, "distance_m": 1000}
            ),
        )
        result = locker._verify_runnerup_via_files()
        assert result is not None
        status, _ = result
        assert status == "too_short"

    def test_returns_fallback_when_all_files_unreadable(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_pull_and_parse_tcx returns None for every file → fallback not_verified."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/run.tcx"]),
        )
        object.__setattr__(locker, "_pull_and_parse_tcx", MagicMock(return_value=None))
        status, _ = locker._verify_runnerup_via_files()
        assert status == "not_verified"


# ---------------------------------------------------------------------------
# _scan_and_fill_week_runnerup
# ---------------------------------------------------------------------------
