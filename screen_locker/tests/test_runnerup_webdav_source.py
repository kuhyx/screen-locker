"""RunnerUp exports are read from the WebDAV drop directory, phone optional.

RunnerUp's WebDAV synchroniser uploads every export to dufs on this machine
(``RUNNERUP_WEBDAV_DIRS``), minutes after the run ends, and endurain-import
moves them to ``processed/``. Reading those files credits the run without the
phone being adb-reachable: on 2026-09-16 the TCX was on disk at 20:08 and the
phone was only plugged in at 20:25.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

_TCX = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap>
        <TotalTimeSeconds>4200.0</TotalTimeSeconds>
        <DistanceMeters>5800.0</DistanceMeters>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""


def _webdav_tree(tmp_path: Path) -> tuple[Path, Path]:
    inbox = tmp_path / "cloud" / "RunnerUp"
    processed = inbox / "processed"
    processed.mkdir(parents=True)
    return inbox, processed


class TestLocalExportDiscovery:
    """``_find_runnerup_exports_for_date`` / ``_has_runnerup_source``."""

    def test_local_files_found_without_adb(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Inbox and processed/ are both searched; adb is never asked."""
        locker = create_locker(mock_tk, tmp_path)
        inbox, processed = _webdav_tree(tmp_path)
        (inbox / "RunnerUp_Pixel_6a_2026-09-16-18-58-28_Running.tcx").write_text(_TCX)
        (processed / "RunnerUp_2026-09-16-18-58-28_Running.tcx").write_text(_TCX)
        (inbox / "RunnerUp_2026-09-16-18-58-28_Running.gpx").write_text("<gpx/>")
        (processed / "RunnerUp_2026-09-01-18-04-41_Running.tcx").write_text(_TCX)
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=False))
        object.__setattr__(locker, "_run_adb", MagicMock())

        with patch(
            "screen_locker._runnerup_verification.RUNNERUP_WEBDAV_DIRS",
            (inbox, processed),
        ):
            assert locker._has_runnerup_source() is True
            found = locker._find_runnerup_exports_for_date("2026-09-16")

        assert found == [
            str(inbox / "RunnerUp_Pixel_6a_2026-09-16-18-58-28_Running.tcx"),
            str(processed / "RunnerUp_2026-09-16-18-58-28_Running.tcx"),
        ]
        locker._run_adb.assert_not_called()

    def test_phone_paths_appended_after_local_when_adb_present(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """With a phone attached the adb listing follows the local copies."""
        locker = create_locker(mock_tk, tmp_path)
        inbox, processed = _webdav_tree(tmp_path)
        (inbox / "RunnerUp_2026-09-16-18-58-28_Running.tcx").write_text(_TCX)
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(
            locker,
            "_run_adb",
            MagicMock(
                return_value=(True, "RunnerUp_2026-09-16-18-58-28_Running.tcx\n")
            ),
        )

        with (
            patch(
                "screen_locker._runnerup_verification.RUNNERUP_WEBDAV_DIRS",
                (inbox, processed),
            ),
            patch(
                "screen_locker._runnerup_verification.RUNNERUP_EXPORT_DIRS",
                ("/sdcard/Documents/RunnerUp",),
            ),
        ):
            found = locker._find_runnerup_exports_for_date("2026-09-16")

        assert found == [
            str(inbox / "RunnerUp_2026-09-16-18-58-28_Running.tcx"),
            "/sdcard/Documents/RunnerUp/RunnerUp_2026-09-16-18-58-28_Running.tcx",
        ]

    def test_no_source_when_dir_missing_and_no_phone(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Neither directory nor phone → no source, verify reports no_phone."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=False))

        with (
            patch(
                "screen_locker._runnerup_verification.RUNNERUP_WEBDAV_DIRS",
                (tmp_path / "absent",),
            ),
            patch(
                "screen_locker._runnerup_verification.check_clock_skew",
                return_value=(True, ""),
            ),
        ):
            assert locker._has_runnerup_source() is False
            status, _ = locker._verify_runnerup_workout()
            assert locker._scan_and_fill_week_runnerup(tmp_path / "log.json") == 0

        assert status == "no_phone"


class TestLocalVerifyAndParse:
    """The local file is parsed in place; the root-DB fallback needs adb."""

    def test_verify_today_from_local_file_without_adb(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A today's TCX on disk verifies with the phone detached."""
        locker = create_locker(mock_tk, tmp_path)
        inbox, processed = _webdav_tree(tmp_path)
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=False))
        object.__setattr__(locker, "_run_adb", MagicMock())

        with (
            patch(
                "screen_locker._runnerup_verification.RUNNERUP_WEBDAV_DIRS",
                (inbox, processed),
            ),
            patch(
                "screen_locker._runnerup_verification.check_clock_skew",
                return_value=(True, ""),
            ),
            patch("screen_locker._runnerup_verification.today_str") as today,
        ):
            today.return_value = "2026-09-16"
            (inbox / "RunnerUp_2026-09-16-18-58-28_Running.tcx").write_text(_TCX)
            status, message = locker._verify_runnerup_workout()

        assert status == "verified"
        assert "5.8 km" in message
        locker._run_adb.assert_not_called()

    def test_no_file_and_no_adb_is_not_verified_without_db_fallback(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """An empty drop dir with no phone cannot fall back to the root DB."""
        locker = create_locker(mock_tk, tmp_path)
        inbox, processed = _webdav_tree(tmp_path)
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=False))
        object.__setattr__(locker, "_verify_runnerup_via_db", MagicMock())

        with (
            patch(
                "screen_locker._runnerup_verification.RUNNERUP_WEBDAV_DIRS",
                (inbox, processed),
            ),
            patch(
                "screen_locker._runnerup_verification.check_clock_skew",
                return_value=(True, ""),
            ),
        ):
            status, message = locker._verify_runnerup_workout()

        assert status == "not_verified"
        assert "not adb-reachable" in message
        locker._verify_runnerup_via_db.assert_not_called()

    def test_pull_and_parse_reads_local_path_in_place(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A path that exists locally is parsed without any adb pull."""
        locker = create_locker(mock_tk, tmp_path)
        tcx = tmp_path / "run.tcx"
        tcx.write_text(_TCX)
        object.__setattr__(locker, "_run_adb", MagicMock())

        data = locker._pull_and_parse_tcx(str(tcx))

        assert data is not None
        assert data["distance_m"] == 5800.0
        locker._run_adb.assert_not_called()
