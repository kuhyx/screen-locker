"""The unified rule sums a day's activities; the root DB and the pure aggregate."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING

import pytest

from screen_locker._walk_tcx import (
    ActivityDay,
    activity_day,
    activity_shortfall,
    walk_day,
)
from screen_locker.tests._activity_helpers import (
    DAY,
    Verifier,
    drop,
    tcx,
    verify,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="verifier")
def verifier_fixture(tmp_path: Path) -> Verifier:
    """A Verifier reading a temporary drop directory."""
    return Verifier(tmp_path)


class TestDaySums:
    """Time AND distance add up across a day's files, whatever their sport."""

    def test_two_15_min_sessions_make_the_bar(self, verifier: Verifier) -> None:
        """A run and a walk of 15 moving minutes each credit together."""
        drop(
            verifier.folder,
            "07-00-00",
            "_Running",
            tcx("Running", "07:00", moving_min=15, metres=900),
        )
        drop(
            verifier.folder,
            "18-00-00",
            "_Walking",
            tcx("Other", "18:00", moving_min=15, metres=900),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "verified"

    def test_two_short_distances_make_the_distance_bar(
        self, verifier: Verifier
    ) -> None:
        """Distance sums per day too: 2 km + 1.6 km is 3.6 km."""
        drop(
            verifier.folder,
            "07-00-00",
            "_Running",
            tcx("Running", "07:00", moving_min=10, metres=2000),
        )
        drop(
            verifier.folder,
            "18-00-00",
            "_Walking",
            tcx("Other", "18:00", moving_min=10, metres=1600),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "verified"

    def test_the_same_activity_from_two_sources_counts_once(
        self, verifier: Verifier
    ) -> None:
        """The WebDAV and phone copies of one export are one activity."""
        body = tcx("Running", "07:00", moving_min=15, metres=900)
        drop(verifier.folder, "07-00-00", "_Running", body)
        drop(verifier.folder, "07-00-01", "_Running", body)
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"

    def test_a_short_day_reports_what_is_missing(
        self, verifier: Verifier, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The shortfall names both bars and what the day had."""
        drop(
            verifier.folder,
            "07-00-00",
            "_Running",
            tcx("Running", "07:00", moving_min=10, metres=800),
        )
        with caplog.at_level(logging.WARNING):
            result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"
        assert "need 3.5+ km or 30+ min moving" in result[1]

    def test_the_completion_time_is_the_activity_that_crossed_the_bar(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        """completed_at is when the day's total crossed the bar, not its last file."""
        drop(
            verifier.folder,
            "07-00-00",
            "_Running",
            tcx("Running", "07:00", moving_min=20, metres=1200),
        )
        drop(
            verifier.folder,
            "12-00-00",
            "_Walking",
            tcx("Other", "12:00", moving_min=10, metres=600),
        )
        drop(
            verifier.folder,
            "18-00-00",
            "_Walking",
            tcx("Other", "18:00", moving_min=10, metres=600),
        )
        log = tmp_path / "log.json"
        assert verifier._try_fill_runnerup_for_date(DAY, log) is True
        (entry,) = json.loads(log.read_text())[DAY]
        crossed = datetime(2026, 10, 10, 12, 10, tzinfo=UTC).timestamp()
        assert entry["workout_data"]["completed_at"] == crossed


class TestRootDbFallback:
    """The root DB path has no trackpoints: wall-clock is all it knows."""

    def test_a_db_row_is_judged_by_its_duration(self, verifier: Verifier) -> None:
        """No moving_seconds in the dict: the recorded duration stands in."""
        row = {"sport": 0, "duration_seconds": 31 * 60, "distance_m": 2000.0}
        assert verifier._validate_runnerup_data(row)[0] == "verified"
        row["duration_seconds"] = 10 * 60
        assert verifier._validate_runnerup_data(row)[0] == "too_short"

    def test_sport_code_does_not_change_the_verdict(self, verifier: Verifier) -> None:
        """Every RunnerUp sport code gets the same answer for the same numbers."""
        base = {"duration_seconds": 31 * 60, "distance_m": 2000.0}
        verdicts = {
            verifier._validate_runnerup_data({**base, "sport": code})[0]
            for code in (-1, 0, 1, 2, 3, 4, 5, 6, 7)
        }
        assert verdicts == {"verified"}


class TestActivityDay:
    """The pure day aggregate."""

    def test_distance_gets_the_gps_tolerance(self) -> None:
        """3.4 km is within 5% of the 3.5 km minimum; 3.3 km is not."""
        near = activity_day([{"distance_m": 3400.0, "moving_seconds": 0.0}])
        assert near.qualifies
        far = activity_day([{"distance_m": 3300.0, "moving_seconds": 0.0}])
        assert not far.qualifies

    def test_the_alias_still_imports(self) -> None:
        """walk_day is the old name of activity_day."""
        assert walk_day is activity_day

    def test_message_styles(self) -> None:
        """A lone run reads like a run, walks like walks, a mix like activities."""
        run = {"sport": 0, "distance_m": 4200.0, "moving_seconds": 1560.0}
        walk = {"walking": True, "distance_m": 2300.0, "moving_seconds": 1680.0}
        assert activity_day([run]).message() == "Running: 4.2 km in 26 min"
        assert activity_day([walk]).message() == (
            "Walking: 1 walk(s), 2.3 km, 28 min moving"
        )
        assert activity_day([run, walk]).message() == (
            "Activity: 2 activities, 6.5 km, 54 min moving"
        )
        assert activity_day([{"sport": 99}]).message().startswith("99:")

    def test_shortfall_text(self) -> None:
        """The shortfall names both ways to qualify."""
        day: ActivityDay = activity_day([{"distance_m": 100.0, "moving_seconds": 60.0}])
        assert activity_shortfall(day).endswith("need 3.5+ km or 30+ min moving")
