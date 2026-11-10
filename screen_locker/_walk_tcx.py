"""One crediting rule for every GPS activity, from its RunnerUp-style TCX export.

A day's activities -- runs and walks, RunnerUp's files and the workout app's
alike -- are summed, and the day counts as the workout once EITHER

* their distance reaches ``MIN_RUN_DISTANCE_KM`` (within the GPS tolerance), OR
* their *moving* time reaches the shared duration bar
  (``WORKOUT_DURATION_ACCEPT_MINUTES``).

The TCX sport and the ``_Walking`` file-name suffix never change the outcome;
they only decide the label a message and the log's ``activity`` field carry
(the phone's history shows it).

**Which files are walks (label only).** RunnerUp's WebDAV and File
synchronisers both export with ``ExportOptions.getDefault()``, whose TCX writer
knows only Running/Biking and writes ``Sport="Other"`` for a walk. The sport
survives only in the file name (``Sport.TapiriikType()``): ``..._Walking.tcx``.
The Strava export variant writes ``Sport="Walking"``, so that counts too.

**Moving time, not elapsed.** A lap's ``TotalTimeSeconds`` is wall-clock: one
real lap reads 101 min for 1 km of standing about. Moving time is summed over
consecutive trackpoint pairs travelled at least at ``MIN_MOVING_SPEED_MPS``:
standing still is too slow. A pair further apart than ``WALK_MAX_GAP_SECONDS``
is a GPS dropout whose motion is unknown and earns nothing -- an activity is
never credited for time nobody saw, so a pause cannot buy a run its duration.
A pair faster than ``MAX_MOVING_SPEED_MPS`` (25 km/h) is a vehicle or a GPS
jump: it counts neither moving time nor distance, so a bus ride earns nothing.
The day's distance is the sum of the surviving pairs (``track_distance_m``),
never the lap's ``DistanceMeters`` total, and an export with no trackpoints
cannot be speed-checked, so it credits nothing. Only the root-DB fallback,
which has no trackpoints at all, is judged by its recorded distance and
duration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import itertools
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._constants import (
    MAX_MOVING_SPEED_MPS,
    MIN_MOVING_SPEED_MPS,
    MIN_RUN_DISTANCE_KM,
    MIN_WORKOUT_DURATION_MINUTES,
    RUNNERUP_DISTANCE_TOLERANCE,
    WALK_MAX_GAP_SECONDS,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)

_TCX_NS = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}"
_WALKING = "Walking"

# RunnerUp's sport codes, for labels only (the label never decides credit).
SPORT_NAMES: dict[int, str] = {
    0: "Running",
    1: "Biking",
    2: "Other",
    3: "Orienteering",
    4: "Walking",
    5: "Treadmill",
    6: "Gym",
    7: "Stationary Bike",
}


def is_walking_export(name: str, sport: str) -> bool:
    """Whether a TCX export is a walk, from its file name or its Sport tag."""
    return name.endswith(f"_{_WALKING}.tcx") or sport == _WALKING


def _stamp(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        _logger.warning("TCX trackpoint has an unparsable time %r; skipped", raw)
        return None


def _trackpoints(activity: ET.Element) -> list[tuple[float, float]]:
    """``(unix time, cumulative metres)`` of every usable trackpoint, in order."""
    points: list[tuple[float, float]] = []
    for point in activity.iter(f"{_TCX_NS}Trackpoint"):
        when = _stamp(point.findtext(f"{_TCX_NS}Time"))
        metres = point.findtext(f"{_TCX_NS}DistanceMeters")
        if when is None or not metres:
            continue
        points.append((when, float(metres)))
    points.sort()
    return points


def track_summary(activity: ET.Element) -> dict[str, Any]:
    """Moving seconds, credited distance and end time, from the trackpoints.

    A pair counts when its points are within ``WALK_MAX_GAP_SECONDS`` and it
    was not travelled faster than ``MAX_MOVING_SPEED_MPS``. It then adds its
    metres to ``track_distance_m``, and its seconds to ``moving_seconds`` too
    when it was travelled at least at ``MIN_MOVING_SPEED_MPS``.
    """
    points = _trackpoints(activity)
    moving = 0.0
    metres = 0.0
    for (t0, d0), (t1, d1) in itertools.pairwise(points):
        gap = t1 - t0
        if not 0 < gap <= WALK_MAX_GAP_SECONDS:
            continue
        speed = (d1 - d0) / gap
        if speed > MAX_MOVING_SPEED_MPS:
            continue
        metres += max(d1 - d0, 0.0)
        if speed >= MIN_MOVING_SPEED_MPS:
            moving += gap
    return {
        "activity_id": activity.findtext(f"{_TCX_NS}Id") or "",
        "moving_seconds": moving,
        "track_distance_m": metres,
        "ended_at": points[-1][0] if points else None,
    }


def distance_qualifies(distance_km: float) -> bool:
    """Whether a distance meets the minimum, with the GPS tolerance."""
    return distance_km * (1 + RUNNERUP_DISTANCE_TOLERANCE) >= MIN_RUN_DISTANCE_KM


def moving_qualifies(moving_minutes: float) -> bool:
    """Whether moving time meets the shared duration bar (leeway included)."""
    return moving_minutes >= WORKOUT_DURATION_ACCEPT_MINUTES


def _distance_metres(activity: dict[str, Any]) -> float:
    """Credited metres; the root-DB path has no trackpoints, so its total stands in."""
    return float(activity.get("track_distance_m", activity.get("distance_m", 0.0)))


def _moving_seconds(activity: dict[str, Any]) -> float:
    """Moving seconds; the root-DB path has no trackpoints, so wall-clock stands in."""
    return float(activity.get("moving_seconds", activity.get("duration_seconds", 0.0)))


@dataclass(frozen=True)
class ActivityDay:
    """A day's activities, summed.

    Attributes:
        legs: Distinct activities (deduplicated by the activity's ``Id``: the
            WebDAV copy and the phone's copy are the same activity).
        moving_minutes: Their summed moving time.
        distance_km: Their summed distance.
        completed_at: Unix time the activity that took the day over the bar
            ended -- when the workout was actually done -- or ``None`` if the
            day never got there (or the activity recorded no end).
        all_walks: Whether every activity was a walk (label only).
        sport: The sport code when the day is a single non-walk activity.
    """

    legs: int
    moving_minutes: float
    distance_km: float
    completed_at: float | None
    all_walks: bool = False
    sport: int = -1

    @property
    def qualifies(self) -> bool:
        """Whether the day counts as its workout: distance OR moving time."""
        return distance_qualifies(self.distance_km) or moving_qualifies(
            self.moving_minutes
        )

    def message(self) -> str:
        """The verification line, in the RunnerUp verifier's own style."""
        if self.all_walks:
            return (
                f"Walking: {self.legs} walk(s), {self.distance_km:.1f} km, "
                f"{self.moving_minutes:.0f} min moving"
            )
        if self.legs == 1:
            name = SPORT_NAMES.get(self.sport, str(self.sport))
            return f"{name}: {self.distance_km:.1f} km in {self.moving_minutes:.0f} min"
        return (
            f"Activity: {self.legs} activities, {self.distance_km:.1f} km, "
            f"{self.moving_minutes:.0f} min moving"
        )


def activity_shortfall(day: ActivityDay) -> str:
    """Why a day's activity did not count yet."""
    return (
        f"{day.message()} -- need {MIN_RUN_DISTANCE_KM:g}+ km or "
        f"{MIN_WORKOUT_DURATION_MINUTES}+ min moving"
    )


def activity_day(activities: Iterable[dict[str, Any]]) -> ActivityDay:
    """Sum parsed exports (``parse_tcx_file`` dicts) into one :class:`ActivityDay`."""
    unique: dict[str, dict[str, Any]] = {}
    for activity in activities:
        unique.setdefault(str(activity.get("activity_id") or id(activity)), activity)
    ordered = sorted(unique.values(), key=lambda a: a.get("ended_at") or 0.0)
    moving = 0.0
    metres = 0.0
    completed_at: float | None = None
    for activity in ordered:
        moving += _moving_seconds(activity)
        metres += _distance_metres(activity)
        if completed_at is None and (
            moving_qualifies(moving / 60) or distance_qualifies(metres / 1000)
        ):
            completed_at = activity.get("ended_at")
    return ActivityDay(
        legs=len(ordered),
        moving_minutes=moving / 60,
        distance_km=metres / 1000,
        completed_at=completed_at,
        all_walks=bool(ordered) and all(a.get("walking") for a in ordered),
        sport=int(ordered[0].get("sport", -1)) if ordered else -1,
    )


# Back-compat names: the walk-only rule these replaced.
WalkDay = ActivityDay
walk_day = activity_day
walk_shortfall = activity_shortfall
