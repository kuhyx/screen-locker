"""Speed cap, lap-only files and the shapes real exports have (dropouts, jitter)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from screen_locker.tests._activity_helpers import (
    DAY,
    Verifier,
    drop,
    tcx,
    tcx_points,
    verify,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="verifier")
def verifier_fixture(tmp_path: Path) -> Verifier:
    """A Verifier reading a temporary drop directory."""
    return Verifier(tmp_path)


def parsed(verifier: Verifier, sport: str, points: list[tuple[int, float]]) -> dict:
    """Drop a track made of exactly ``points`` and return its parsed summary."""
    drop(verifier.folder, "08-00-00", "_Running", tcx_points(sport, "08:00", points))
    (path,) = verifier._find_runnerup_exports_for_date(DAY)
    data = verifier._pull_and_parse_tcx(path)
    assert data is not None
    return data


class TestLapOnlyExport:
    """An export with laps but no trackpoints has no moving time to credit."""

    def test_wall_clock_alone_credits_nothing(self, verifier: Verifier) -> None:
        """40 min on the lap clock, 1 km, no trackpoints: too short."""
        body = (
            '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/'
            'TrainingCenterDatabase/v2"><Activities><Activity Sport="Running">'
            "<Id>2026-10-10T08:00</Id><Lap><TotalTimeSeconds>2400</TotalTimeSeconds>"
            "<DistanceMeters>1000</DistanceMeters></Lap></Activity></Activities>"
            "</TrainingCenterDatabase>"
        )
        drop(verifier.folder, "08-00-00", "_Running", body)
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"


class TestSpeedCap:
    """Segments faster than 25 km/h count neither moving time nor distance."""

    def test_a_car_trip_credits_nothing(self, verifier: Verifier) -> None:
        """10 km at 40 km/h (15 min) is a vehicle, not a workout."""
        drop(
            verifier.folder,
            "08-00-00",
            "_Walking",
            tcx("Walking", "08:00", moving_min=15, metres=10000),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"

    def test_one_gps_jump_drops_only_its_window(self, verifier: Verifier) -> None:
        """A 60 km/h jump inside a 3 m/s run loses its 10 s window and no more."""
        points = [(s, s * 3.0 + (83.0 if s > 600 else 0.0)) for s in range(0, 1201, 5)]
        data = parsed(verifier, "Running", points)
        assert data["moving_seconds"] == pytest.approx(1190)
        assert data["track_distance_m"] == pytest.approx(3570)
        result = verify(verifier)
        assert result is not None
        assert result[0] == "verified"

    def test_a_car_with_sparse_fixes_still_credits_nothing(
        self, verifier: Verifier
    ) -> None:
        """40 km/h with a fix every 60 s is dropped as a dropout too."""
        points = [(s, s * 11.1) for s in range(0, 1500, 60)]
        drop(
            verifier.folder,
            "08-00-00",
            "_Walking",
            tcx_points("Walking", "08:00", points),
        )
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"


class TestRealRunShapes:
    """Shapes seen in real exports (checked on 27 days of them) stay whole."""

    def test_sparse_fixes_every_18_seconds_still_count(
        self, verifier: Verifier
    ) -> None:
        """Old RunnerUp files have a fix every 15-60 s: a 4 km run in 42 min."""
        points = [(s, s * 1.6) for s in range(0, 2520, 18)]
        data = parsed(verifier, "Running", points)
        assert data["track_distance_m"] == pytest.approx(points[-1][1])
        assert data["moving_seconds"] == pytest.approx(points[-1][0])

    def test_a_gps_dropout_at_running_pace_is_kept(self, verifier: Verifier) -> None:
        """A 2 minute signal loss with the runner still moving keeps both."""
        points = [(s, s * 1.7) for s in range(600)]
        points += [(s, s * 1.7) for s in range(720, 1320)]
        data = parsed(verifier, "Running", points)
        assert data["track_distance_m"] == pytest.approx(1319 * 1.7, rel=0.01)
        assert data["moving_seconds"] == pytest.approx(1319, rel=0.01)

    def test_a_standing_pause_earns_nothing(self, verifier: Verifier) -> None:
        """A 5 minute gap with ~no movement adds no time (and ~no metres)."""
        points = [(s, s * 1.7) for s in range(600)]
        points += [(s, 600 * 1.7 + 2) for s in range(900, 910)]
        data = parsed(verifier, "Running", points)
        assert data["moving_seconds"] == pytest.approx(599, abs=12)

    def test_one_second_jitter_is_smoothed(self, verifier: Verifier) -> None:
        """A 1 s fix 12 m ahead (12 m/s alone) is noise inside a 3 m/s run."""
        points = [(s, s * 3.0 + (12.0 if not s % 50 else 0.0)) for s in range(600)]
        data = parsed(verifier, "Running", points)
        assert data["track_distance_m"] > 0.97 * points[-1][1]
