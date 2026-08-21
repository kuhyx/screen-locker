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
