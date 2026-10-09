"""A day's RunnerUp walks are summed into one workout; never one file at a time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker._runnerup_verification import RunnerUpVerificationMixin

if TYPE_CHECKING:
    from pathlib import Path

_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_DAY = "2026-10-10"


def tcx(sport: str, minutes: int, start: str, speed: float = 1.3) -> str:
    """A RunnerUp-shaped export: trackpoints every 5 s at ``speed`` m/s."""
    begin = datetime.fromisoformat(f"{_DAY}T{start}:00+00:00")
    points = "".join(
        f"<Trackpoint><Time>{(begin + timedelta(seconds=s)).isoformat()}</Time>"
        f"<DistanceMeters>{s * speed:.1f}</DistanceMeters></Trackpoint>"
        for s in range(0, minutes * 60 + 1, 5)
    )
    return (
        f'<TrainingCenterDatabase xmlns="{_NS}"><Activities>'
        f'<Activity Sport="{sport}"><Id>{_DAY}T{start}</Id><Lap>'
        f"<TotalTimeSeconds>{minutes * 60}</TotalTimeSeconds>"
        f"<DistanceMeters>{minutes * 60 * speed}</DistanceMeters>"
        f"<Track>{points}</Track></Lap></Activity></Activities>"
        "</TrainingCenterDatabase>"
    )


class Verifier(RunnerUpVerificationMixin):
    """The real mixin, reading one temporary drop directory and no phone."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.adb = MagicMock(return_value=(False, ""))

    def _has_adb_device(self) -> bool:
        return False

    def _run_adb(self, args: list[str]) -> tuple[bool, str]:
        return self.adb(args)

    def _find_runnerup_exports_for_date(self, date_str: str) -> list[str]:
        return sorted(str(p) for p in self.folder.glob(f"*{date_str}*.tcx"))


def drop(folder: Path, name: str, body: str) -> None:
    (folder / f"RunnerUp_Pixel_6a_{_DAY}-{name}.tcx").write_text(body)


@pytest.fixture
def verifier(tmp_path: Path) -> Verifier:
    return Verifier(tmp_path)


class TestParse:
    def test_a_walk_is_flagged_by_its_file_name(self, verifier: Verifier) -> None:
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 10, "08:00"))
        (path,) = verifier._find_runnerup_exports_for_date(_DAY)
        data = verifier._pull_and_parse_tcx(path)
        assert data is not None
        assert data["walking"] is True
        assert data["moving_seconds"] == pytest.approx(600)

    def test_a_pulled_copy_keeps_the_phone_name(self, verifier: Verifier) -> None:
        """adb pulls into ``activity.tcx``; the remote name still decides."""
        body = tcx("Other", 10, "08:00")

        def pull(args: list[str]) -> tuple[bool, str]:
            from pathlib import Path

            Path(args[2]).write_text(body)
            return True, ""

        verifier.adb.side_effect = pull
        data = verifier._pull_and_parse_tcx("/sdcard/RunnerUp_x_Walking.tcx")
        assert data is not None
        assert data["walking"] is True

    def test_a_failed_pull_is_none(self, verifier: Verifier) -> None:
        assert verifier._pull_and_parse_tcx("/sdcard/RunnerUp_x_Walking.tcx") is None


class TestVerifyToday:
    def _verify(self, verifier: Verifier) -> tuple[str, str] | None:
        with patch("screen_locker._runnerup_verification.today_str", return_value=_DAY):
            return verifier._verify_runnerup_via_files()

    def test_walks_summing_to_the_bar_verify(self, verifier: Verifier) -> None:
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 25, "08:00"))
        drop(verifier.folder, "17-00-00_Walking", tcx("Other", 20, "17:00"))
        result = self._verify(verifier)
        assert result is not None
        assert result[0] == "verified"
        assert result[1].startswith("Walking: 2 walk(s)")

    def test_one_long_elapsed_walk_is_judged_by_moving_time(
        self, verifier: Verifier
    ) -> None:
        """60 min on the clock, standing still: not a workout."""
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 60, "08:00", 0.1))
        assert self._verify(verifier) == (
            "too_short",
            "Walking: 1 walk(s), 0.4 km, 0 min moving -- need 40+ min moving",
        )

    def test_a_run_still_verifies_beside_short_walks(self, verifier: Verifier) -> None:
        drop(verifier.folder, "07-00-00_Walking", tcx("Other", 10, "07:00"))
        drop(verifier.folder, "18-00-00_Running", tcx("Running", 45, "18:00", 2.5))
        result = self._verify(verifier)
        assert result is not None
        assert result[0] == "verified"
        assert result[1].startswith("Running")

    def test_a_short_run_outranks_the_walk_shortfall(self, verifier: Verifier) -> None:
        drop(verifier.folder, "07-00-00_Walking", tcx("Other", 10, "07:00"))
        drop(verifier.folder, "18-00-00_Running", tcx("Running", 5, "18:00", 2.5))
        result = self._verify(verifier)
        assert result is not None
        assert result[0] == "too_short"
        assert result[1].startswith("Run was")


class TestBackfill:
    def test_walks_are_logged_as_one_workout(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 25, "08:00"))
        drop(verifier.folder, "17-00-00_Walking", tcx("Other", 20, "17:00"))
        log = tmp_path / "log.json"
        ingested = MagicMock()
        assert verifier._try_fill_runnerup_for_date(_DAY, log, ingested) is True
        (entry,) = json.loads(log.read_text())[_DAY]
        data = entry["workout_data"]
        assert data["type"] == "runnerup_verified"
        assert data["activity"] == "walking"
        assert data["duration_minutes"] == pytest.approx(45)
        assert (
            data["completed_at"]
            == datetime(2026, 10, 10, 17, 20, tzinfo=UTC).timestamp()
        )
        ingested.assert_called_once()
        # The same day again is the same slot: nothing new.
        assert verifier._try_fill_runnerup_for_date(_DAY, log, ingested) is False

    def test_walks_short_of_the_bar_log_nothing(
        self,
        verifier: Verifier,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 30, "08:00"))
        log = tmp_path / "log.json"
        with caplog.at_level(logging.WARNING):
            assert verifier._try_fill_runnerup_for_date(_DAY, log) is False
        assert "do not count yet" in caplog.text
        assert not log.exists()

    def test_a_run_records_its_end_time(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        drop(verifier.folder, "18-00-00_Running", tcx("Running", 45, "18:00", 2.5))
        log = tmp_path / "log.json"
        assert verifier._try_fill_runnerup_for_date(_DAY, log) is True
        (entry,) = json.loads(log.read_text())[_DAY]
        end = datetime(2026, 10, 10, 18, 45, tzinfo=UTC).timestamp()
        assert entry["workout_data"]["completed_at"] == end
