"""Tests for ``_walk_tcx``: which exports are walks, and their moving time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any
import xml.etree.ElementTree as ET

import pytest

from screen_locker._walk_tcx import (
    is_walking_export,
    track_summary,
    walk_day,
    walk_shortfall,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_START = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)


def activity(points: Sequence[tuple[float, str | None, str | None]]) -> ET.Element:
    """An Activity of ``(seconds after start, metres, raw time override)``.

    A raw time of ``"-"`` leaves the point without a time.
    """
    root = ET.Element(f"{{{_NS}}}Activity", Sport="Other")
    ET.SubElement(root, f"{{{_NS}}}Id").text = "A1"
    track = ET.SubElement(ET.SubElement(root, f"{{{_NS}}}Lap"), f"{{{_NS}}}Track")
    for sec, metres, raw in points:
        point = ET.SubElement(track, f"{{{_NS}}}Trackpoint")
        if raw != "-":
            stamp = raw or (_START + timedelta(seconds=sec)).isoformat()
            ET.SubElement(point, f"{{{_NS}}}Time").text = stamp
        if metres:
            ET.SubElement(point, f"{{{_NS}}}DistanceMeters").text = metres
    return root


def walk(seconds: int, speed: float = 1.3) -> ET.Element:
    """A steady walk sampled every 5 s."""
    return activity([(s, f"{s * speed:.1f}", None) for s in range(0, seconds + 1, 5)])


class TestIsWalkingExport:
    def test_the_file_name_names_the_sport(self) -> None:
        """RunnerUp's default export writes Sport="Other"; the name says Walking."""
        assert is_walking_export("RunnerUp_2026-10-10-08-00-00_Walking.tcx", "Other")

    def test_the_strava_variant_tags_the_activity(self) -> None:
        assert is_walking_export("RunnerUp_2026-10-10-08-00-00.tcx", "Walking")

    def test_other_alone_is_not_a_walk(self) -> None:
        assert not is_walking_export("RunnerUp_2026-10-10_Running.tcx", "Other")


class TestTrackSummary:
    def test_walking_speed_is_moving(self) -> None:
        summary = track_summary(walk(600))
        assert summary["moving_seconds"] == pytest.approx(600)
        assert summary["activity_id"] == "A1"
        assert summary["ended_at"] == (_START + timedelta(seconds=600)).timestamp()

    def test_standing_and_vehicles_are_not_moving(self) -> None:
        assert track_summary(walk(600, speed=0.1))["moving_seconds"] == 0
        assert track_summary(walk(600, speed=8.0))["moving_seconds"] == 0

    def test_a_gps_dropout_earns_nothing(self) -> None:
        """Two points 100 s apart at walking pace: motion unseen, not counted."""
        summary = track_summary(activity([(0, "0.1", None), (100, "130", None)]))
        assert summary["moving_seconds"] == 0

    def test_unusable_points_are_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        points = [
            (0, "0.1", None),
            (5, None, None),  # no distance
            (6, "8", "-"),  # no time
            (7, "9", "not-a-time"),
            (10, "13", None),
        ]
        with caplog.at_level(logging.WARNING):
            summary = track_summary(activity(points))
        assert summary["moving_seconds"] == pytest.approx(10)
        assert "unparsable time" in caplog.text

    def test_no_points_has_no_end(self) -> None:
        summary = track_summary(activity([]))
        assert summary == {"activity_id": "A1", "moving_seconds": 0.0, "ended_at": None}


def leg(
    ident: str, minutes: float, ended: float, metres: float = 2000
) -> dict[str, Any]:
    return {
        "activity_id": ident,
        "moving_seconds": minutes * 60,
        "ended_at": ended,
        "distance_m": metres,
    }


class TestWalkDay:
    def test_legs_sum_and_complete_when_the_bar_is_crossed(self) -> None:
        day = walk_day([leg("b", 20, 200.0), leg("a", 25, 100.0), leg("c", 5, 300.0)])
        assert day.legs == 3
        assert day.moving_minutes == pytest.approx(50)
        assert day.distance_km == pytest.approx(6)
        assert day.completed_at == 200.0  # a (25) + b (20) crosses 40 at b's end
        assert day.qualifies
        assert day.message() == "Walking: 3 walk(s), 6.0 km, 50 min moving"

    def test_the_same_walk_from_two_sources_counts_once(self) -> None:
        copy = leg("same", 30, 100.0)
        day = walk_day([copy, dict(copy)])
        assert day.legs == 1
        assert not day.qualifies
        assert day.completed_at is None

    def test_a_walk_without_id_or_end_still_counts(self) -> None:
        anonymous = {"moving_seconds": 45 * 60}
        day = walk_day([anonymous])
        assert day.legs == 1
        assert day.qualifies
        assert day.completed_at is None

    def test_shortfall_says_what_is_missing(self) -> None:
        text = walk_shortfall(walk_day([leg("a", 30, 1.0)]))
        assert text.endswith("need 40+ min moving")
