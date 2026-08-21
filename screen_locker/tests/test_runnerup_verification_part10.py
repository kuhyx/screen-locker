"""Tests for _scan_and_fill_week_runnerup's skip and error paths.

Split out of test_runnerup_verification_part7.py for the 250-line cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._log_io import load_workout_log
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


class TestScanAndFillWeekRunnerupSkips:
    """Days the scan declines to fill, and failures it survives."""

    def test_skips_date_when_no_exports(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No exports for a date → date skipped, count stays 0."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=[]),
        )
        assert locker._scan_and_fill_week_runnerup(log_file) == 0

    def test_skips_unreadable_tcx(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_pull_and_parse_tcx returns None → remote skipped, not filled."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_find_runnerup_exports_for_date",
            MagicMock(return_value=["/sdcard/run.tcx"]),
        )
        object.__setattr__(locker, "_pull_and_parse_tcx", MagicMock(return_value=None))
        assert locker._scan_and_fill_week_runnerup(log_file) == 0

    def test_skips_not_verified_export(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_validate_runnerup_data returns not-verified → date not filled.

        Both duration and distance are held under their minimums -- the
        criteria are an OR, so a fixture qualifying on either alone would
        verify instead of exercising the not-verified path this test is
        about.
        """
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
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
        assert locker._scan_and_fill_week_runnerup(log_file) == 0

    def test_rescanning_an_already_filled_day_is_a_no_op(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A day whose run is already logged isn't appended twice (dedup)."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")

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
        object.__setattr__(
            locker,
            "_validate_runnerup_data",
            MagicMock(return_value=("verified", "ok")),
        )

        with patch(
            "screen_locker._log_mixin.compute_entry_hmac",
            return_value="sig",
        ):
            first = locker._try_fill_runnerup_for_date("2026-07-13", log_file)
            second = locker._try_fill_runnerup_for_date("2026-07-13", log_file)

        assert first is True
        assert second is False
        assert len(load_workout_log(log_file)["2026-07-13"]) == 1

    def test_save_error_is_swallowed_not_raised(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An OSError saving the log only warns — the scan still completes.

        Persistence now lives in the write chokepoint (``write_signed_entry``),
        which logs and swallows save errors rather than propagating them.
        """
        locker = create_locker(mock_tk, tmp_path)
        fail_log = tmp_path / "log.json"
        fail_log.write_text("{}")

        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
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
        object.__setattr__(
            locker,
            "_validate_runnerup_data",
            MagicMock(return_value=("verified", "ok")),
        )

        with (
            patch(
                "screen_locker._log_mixin.compute_entry_hmac",
                return_value="sig",
            ),
            patch(
                "screen_locker._log_mixin.json.dump",
                side_effect=OSError("disk full"),
            ),
        ):
            result = locker._scan_and_fill_week_runnerup(fail_log)

        # The append still reports success; only the save failure is warned.
        assert result >= 1
