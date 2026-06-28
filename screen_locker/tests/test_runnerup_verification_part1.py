"""Tests for RunnerUpVerificationMixin in _runnerup_verification.py."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

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

    def test_too_short_duration_returns_too_short(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Duration below MIN_RUN_DURATION_MINUTES → too_short with 'min' in message."""
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 60, "distance_m": 6000}
        )
        assert status == "too_short"
        assert "min" in msg

    def test_too_short_distance_returns_too_short(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Distance below MIN_RUN_DISTANCE_KM → too_short with 'km' in message."""
        locker = create_locker(mock_tk, tmp_path)
        status, msg = locker._validate_runnerup_data(
            {"sport": 0, "duration_seconds": 2400, "distance_m": 100}
        )
        assert status == "too_short"
        assert "km" in msg

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


class TestParseTcx:
    """Tests for _parse_tcx (lines 109-134)."""

    def test_parses_valid_running_tcx(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Valid Running TCX returns correct sport/duration/distance dict."""
        locker = create_locker(mock_tk, tmp_path)
        path = _write_tcx(tmp_path, _TCX_RUNNING)
        result = locker._parse_tcx(path)
        assert result is not None
        assert result["sport"] == 0  # Running
        assert result["duration_seconds"] == 2400
        assert result["distance_m"] == 6000.0

    def test_parse_error_returns_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Malformed XML is caught by ParseError; returns None."""
        locker = create_locker(mock_tk, tmp_path)
        path = _write_tcx(tmp_path, "<not-valid xml << ")
        assert locker._parse_tcx(path) is None

    def test_missing_activity_element_returns_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """TCX with no <Activity> element returns None."""
        locker = create_locker(mock_tk, tmp_path)
        tcx = """\
<?xml version="1.0"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
</TrainingCenterDatabase>
"""
        path = _write_tcx(tmp_path, tcx)
        assert locker._parse_tcx(path) is None

    def test_multi_lap_sums_correctly(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Two laps: totals are summed across both."""
        locker = create_locker(mock_tk, tmp_path)
        path = _write_tcx(tmp_path, _TCX_MULTI_LAP)
        result = locker._parse_tcx(path)
        assert result is not None
        assert result["duration_seconds"] == 2400
        assert result["distance_m"] == 6000.0


# ---------------------------------------------------------------------------
# _find_runnerup_exports_for_date
# ---------------------------------------------------------------------------


class TestFindRunnerupExportsForDate:
    """Tests for _find_runnerup_exports_for_date (lines 77-88)."""

    def test_returns_empty_when_adb_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_run_adb returning False → empty list."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_run_adb", MagicMock(return_value=(False, "")))
        assert locker._find_runnerup_exports_for_date("2024-03-15") == []

    def test_returns_empty_when_no_matching_files(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """ADB listing with no date-matching .tcx files → empty list."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(return_value=(True, "RunnerUp_2024-01-01-10-00-00.tcx\n")),
        )
        assert locker._find_runnerup_exports_for_date("2024-03-15") == []

    def test_returns_matching_tcx_files(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Matching filename with date string → path included in result."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(return_value=(True, "RunnerUp_2024-03-15-10-30-00_act.tcx\n")),
        )
        result = locker._find_runnerup_exports_for_date("2024-03-15")
        assert len(result) >= 1
        assert "2024-03-15" in result[0]
        assert result[0].endswith(".tcx")

    def test_deduplicates_across_dirs(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Same remote path appearing in two dirs is not duplicated."""
        locker = create_locker(mock_tk, tmp_path)
        # Both export dirs return the same filename (different dirs → different paths)
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(return_value=(True, "RunnerUp_2024-03-15-10-30-00_act.tcx\n")),
        )

        result = locker._find_runnerup_exports_for_date("2024-03-15")
        # Paths come from different dirs so both are included, but no duplicates
        assert len(result) == len(set(result))

    def test_skips_empty_listing(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Empty stdout from ADB is skipped without adding entries."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_run_adb", MagicMock(return_value=(True, "   \n")))
        assert locker._find_runnerup_exports_for_date("2024-03-15") == []


# ---------------------------------------------------------------------------
# _pull_and_parse_tcx
# ---------------------------------------------------------------------------


class TestPullAndParseTcx:
    """Tests for _pull_and_parse_tcx (lines 92-101)."""

    def test_returns_none_when_pull_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Failed adb pull → None returned."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_run_adb", MagicMock(return_value=(False, "")))
        assert locker._pull_and_parse_tcx("/sdcard/some.tcx") is None

    def test_returns_none_when_file_not_written(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """adb pull succeeds but local file absent (race) → None."""
        locker = create_locker(mock_tk, tmp_path)
        # _run_adb returns True but does not actually write the file.
        object.__setattr__(locker, "_run_adb", MagicMock(return_value=(True, "")))
        assert locker._pull_and_parse_tcx("/sdcard/some.tcx") is None

    def test_returns_parsed_data_on_success(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Successful pull + valid TCX → parsed activity dict."""
        locker = create_locker(mock_tk, tmp_path)
        tcx_src = tmp_path / "source.tcx"
        tcx_src.write_text(_TCX_RUNNING)

        def _fake_pull(args: list[str]) -> tuple[bool, str]:
            if args[0] == "pull":
                shutil.copy(str(tcx_src), args[2])
                return True, ""
            return True, ""

        object.__setattr__(locker, "_run_adb", MagicMock(side_effect=_fake_pull))
        result = locker._pull_and_parse_tcx("/sdcard/activity.tcx")
        assert result is not None
        assert result["sport"] == 0
        assert result["duration_seconds"] == 2400


# ---------------------------------------------------------------------------
# _verify_runnerup_via_files
# ---------------------------------------------------------------------------


