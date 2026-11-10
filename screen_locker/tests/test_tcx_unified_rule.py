"""One crediting rule for every GPS activity: sport and file name never matter.

A day's activities (runs, walks, RunnerUp's files and the workout app's alike)
are summed and credit once their distance reaches ``MIN_RUN_DISTANCE_KM`` (with
the GPS tolerance) OR their *moving* time reaches the shared duration bar.
Wall-clock time never counts: a pause or a standing-still stretch earns
nothing. Everything runs on temporary directories.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from screen_locker.tests._activity_helpers import DAY, Verifier, drop, tcx, verify

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="verifier")
def verifier_fixture(tmp_path: Path) -> Verifier:
    """A Verifier reading a temporary drop directory."""
    return Verifier(tmp_path)


class TestRequiredCases:
    """The four cases kuhy named when he unified runs and walks."""

    def test_a_walking_file_of_3_6_km_in_40_min_is_credited(
        self, verifier: Verifier
    ) -> None:
        """(a) A Walking-sport export at 3.6 km / 40 min credits."""
        drop(
            verifier.folder,
            "08-00-00",
            "_Walking",
            tcx("Walking", "08:00", moving_min=40, metres=3600),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "verified"

    def test_a_walking_file_of_3_6_km_in_18_min_is_credited_by_distance(
        self, verifier: Verifier
    ) -> None:
        """(a) Distance alone credits a walk, as it always did a run."""
        drop(
            verifier.folder,
            "08-00-00",
            "_Walking",
            tcx("Walking", "08:00", moving_min=18, metres=3600),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "verified"

    def test_a_running_file_with_31_min_moving_and_2_km_is_credited(
        self, verifier: Verifier
    ) -> None:
        """(b) Moving time alone credits a run."""
        drop(
            verifier.folder,
            "18-00-00",
            "_Running",
            tcx("Running", "18:00", moving_min=31, metres=2000),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "verified"

    def test_a_pause_does_not_buy_a_run_its_duration(self, verifier: Verifier) -> None:
        """(c) 24 min moving + 10 min pause = 34 min wall-clock: not credited.

        (24 not 25: the duration bar is 30 minus the 5 minute leeway, so a
        full 25 minutes of motion DOES credit.)
        """
        drop(
            verifier.folder,
            "18-00-00",
            "_Running",
            tcx("Running", "18:00", moving_min=24, metres=1600, pause_min=10),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"

    def test_a_pause_does_not_buy_a_run_its_log_entry(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        """(c) The backfill path agrees: nothing is logged."""
        drop(
            verifier.folder,
            "18-00-00",
            "_Running",
            tcx("Running", "18:00", moving_min=24, metres=1600, pause_min=10),
        )
        log = tmp_path / "log.json"
        assert verifier._try_fill_runnerup_for_date(DAY, log) is False
        assert not log.exists()


_TRACKS = {
    "qualifying_by_time": {"moving_min": 31, "metres": 2000},
    "qualifying_by_distance": {"moving_min": 18, "metres": 3600},
    "paused_short": {"moving_min": 24, "metres": 1600, "pause_min": 10},
    "short": {"moving_min": 10, "metres": 800},
}
_DRESSINGS = [
    ("Running", "_Running"),
    ("Walking", "_Walking"),
    ("Other", "_Walking"),
    ("Other", ""),
    ("Biking", ""),
]


class TestSportAndNameNeverMatter:
    """(d) The same track gives the same outcome under any sport or file name."""

    @pytest.mark.parametrize("track", sorted(_TRACKS))
    def test_status_and_log_are_identical(self, track: str, tmp_path: Path) -> None:
        """Every dressing of one track verifies, logs and credits alike."""
        outcomes = set()
        for index, (sport, suffix) in enumerate(_DRESSINGS):
            folder = tmp_path / f"d{index}"
            folder.mkdir()
            verifier = Verifier(folder)
            drop(folder, "08-00-00", suffix, tcx(sport, "08:00", **_TRACKS[track]))
            status = verify(verifier)
            assert status is not None
            log = folder / "log.json"
            filled = verifier._try_fill_runnerup_for_date(DAY, log)
            credited = (
                json.loads(log.read_text())[DAY][0]["workout_data"]["completed_at"]
                if filled
                else None
            )
            outcomes.add((status[0], filled, credited))
        assert len(outcomes) == 1

    def test_the_activity_label_is_kept_but_never_decides(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        """A walk keeps ``activity: walking`` in the log for the phone's display."""
        drop(
            verifier.folder,
            "08-00-00",
            "_Walking",
            tcx("Other", "08:00", moving_min=31, metres=2000),
        )
        log = tmp_path / "log.json"
        assert verifier._try_fill_runnerup_for_date(DAY, log) is True
        (entry,) = json.loads(log.read_text())[DAY]
        assert entry["workout_data"]["activity"] == "walking"
        assert entry["workout_data"]["type"] == "runnerup_verified"
