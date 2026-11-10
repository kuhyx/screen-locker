"""A day's RunnerUp walks are summed into one workout; never one file at a time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from screen_locker._runnerup_verification import RunnerUpVerificationMixin

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
    """Write a RunnerUp-named TCX export for the test day into the drop folder."""
    (folder / f"RunnerUp_Pixel_6a_{_DAY}-{name}.tcx").write_text(body)


@pytest.fixture(name="verifier")
def verifier_fixture(tmp_path: Path) -> Verifier:
    """A Verifier reading a temporary drop directory."""
    return Verifier(tmp_path)


class TestParse:
    """Groups parsing a pulled TCX export into its walking flag and moving time."""

    def test_a_walk_is_flagged_by_its_file_name(self, verifier: Verifier) -> None:
        """A file named *_Walking is flagged as a walk even when the TCX sport says Other."""
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
            """Fake adb pull that writes the TCX body to the local destination."""
            Path(args[2]).write_text(body)
            return True, ""

        verifier.adb.side_effect = pull
        data = verifier._pull_and_parse_tcx("/sdcard/RunnerUp_x_Walking.tcx")
        assert data is not None
        assert data["walking"] is True

    def test_a_failed_pull_is_none(self, verifier: Verifier) -> None:
        """When the adb pull fails the parse returns None."""
        assert verifier._pull_and_parse_tcx("/sdcard/RunnerUp_x_Walking.tcx") is None


class TestVerifyToday:
    """Groups the verdict over all of the day's RunnerUp exports."""

    def _verify(self, verifier: Verifier) -> tuple[str, str] | None:
        with patch("screen_locker._runnerup_verification.today_str", return_value=_DAY):
            return verifier._verify_runnerup_via_files()

    def test_walks_summing_to_the_bar_verify(self, verifier: Verifier) -> None:
        """Several short walks whose moving time sums past the bar verify together."""
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 15, "08:00"))
        drop(verifier.folder, "17-00-00_Walking", tcx("Other", 12, "17:00"))
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
            "Walking: 1 walk(s), 0.4 km, 0 min moving -- need 3.5+ km or 30+ min moving",
        )

    def test_a_run_beside_short_walks_is_one_summed_day(
        self, verifier: Verifier
    ) -> None:
        """A long enough run verifies even when the day also has short walks."""
        drop(verifier.folder, "07-00-00_Walking", tcx("Other", 10, "07:00"))
        drop(verifier.folder, "18-00-00_Running", tcx("Running", 45, "18:00", 2.5))
        result = self._verify(verifier)
        assert result is not None
        assert result[0] == "verified"
        assert result[1].startswith("Activity: 2 activities")

    def test_a_short_run_and_short_walks_share_one_shortfall(
        self, verifier: Verifier
    ) -> None:
        """A too-short run and short walks are summed into one shortfall."""
        drop(verifier.folder, "07-00-00_Walking", tcx("Other", 10, "07:00"))
        drop(verifier.folder, "18-00-00_Running", tcx("Running", 5, "18:00", 2.5))
        result = self._verify(verifier)
        assert result is not None
        assert result[0] == "too_short"
        assert result[1].startswith("Activity: 2 activities")
        assert "need 3.5+ km or 30+ min moving" in result[1]


class TestBackfill:
    """Groups backfilling the day's RunnerUp activity into log.json."""

    def test_walks_are_logged_as_one_workout(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        """A day's walks are logged as a single workout ending at the last walk, and not again."""
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 15, "08:00"))
        drop(verifier.folder, "17-00-00_Walking", tcx("Other", 12, "17:00"))
        log = tmp_path / "log.json"
        ingested = MagicMock()
        assert verifier._try_fill_runnerup_for_date(_DAY, log, ingested) is True
        (entry,) = json.loads(log.read_text())[_DAY]
        data = entry["workout_data"]
        assert data["type"] == "runnerup_verified"
        assert data["activity"] == "walking"
        assert data["duration_minutes"] == pytest.approx(27)
        assert (
            data["completed_at"]
            == datetime(2026, 10, 10, 17, 12, tzinfo=UTC).timestamp()
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
        """Walks short of the bar log nothing and warn that they do not count yet."""
        drop(verifier.folder, "08-00-00_Walking", tcx("Other", 20, "08:00"))
        log = tmp_path / "log.json"
        with caplog.at_level(logging.WARNING):
            assert verifier._try_fill_runnerup_for_date(_DAY, log) is False
        assert "does not count yet" in caplog.text
        assert not log.exists()

    def test_a_run_records_its_end_time(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        """A logged run records its end time as completed_at."""
        drop(verifier.folder, "18-00-00_Running", tcx("Running", 45, "18:00", 2.5))
        log = tmp_path / "log.json"
        assert verifier._try_fill_runnerup_for_date(_DAY, log) is True
        (entry,) = json.loads(log.read_text())[_DAY]
        end = datetime(2026, 10, 10, 18, 45, tzinfo=UTC).timestamp()
        assert entry["workout_data"]["completed_at"] == end
