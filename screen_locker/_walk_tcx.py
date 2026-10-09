"""Walking in RunnerUp TCX exports: which files are walks, and their moving time.

A day's walking counts as the workout once its walks -- usually separate
commute legs, one file each -- add up to ``WALK_MIN_MOVING_MINUTES`` of
*moving* time.

**Which files are walks.** RunnerUp's WebDAV and File synchronisers both
export with ``ExportOptions.getDefault()``, whose TCX writer knows only
Running/Biking and writes ``Sport="Other"`` for a walk. The sport survives
only in the file name (``Sport.TapiriikType()``): ``..._Walking.tcx``. The
Strava export variant writes ``Sport="Walking"``, so that counts too.
``Other`` alone is not a walk: it is every sport RunnerUp cannot name.

**Moving time, not elapsed.** A lap's ``TotalTimeSeconds`` is wall-clock: one
real lap reads 101 min for 1 km of standing about. Moving time is summed over
consecutive trackpoint pairs whose speed is walking speed
(``WALK_SPEED_MPS``): standing still is too slow, a tram or a bus too fast.
A pair further apart than ``WALK_MAX_GAP_SECONDS`` is a GPS dropout whose
motion is unknown and earns nothing -- the walk is never credited for time
nobody saw.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import itertools
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._constants import (
    WALK_MAX_GAP_SECONDS,
    WALK_MIN_MOVING_MINUTES,
    WALK_SPEED_MPS,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)

_TCX_NS = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}"
_WALKING = "Walking"


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
    """Moving seconds and end time of one activity, from its trackpoints."""
    points = _trackpoints(activity)
    slow, fast = WALK_SPEED_MPS
    moving = 0.0
    for (t0, d0), (t1, d1) in itertools.pairwise(points):
        gap = t1 - t0
        if 0 < gap <= WALK_MAX_GAP_SECONDS and slow <= (d1 - d0) / gap <= fast:
            moving += gap
    return {
        "activity_id": activity.findtext(f"{_TCX_NS}Id") or "",
        "moving_seconds": moving,
        "ended_at": points[-1][0] if points else None,
    }


@dataclass(frozen=True)
class WalkDay:
    """A day's walks, summed.

    Attributes:
        legs: Distinct walks (deduplicated by the activity's ``Id``: the
            WebDAV copy and the phone's copy are the same walk).
        moving_minutes: Their summed moving time.
        distance_km: Their summed distance.
        completed_at: Unix time the walk that crossed the bar ended -- when
            the workout was actually done -- or ``None`` if it never did.
    """

    legs: int
    moving_minutes: float
    distance_km: float
    completed_at: float | None

    @property
    def qualifies(self) -> bool:
        """Whether the day's walking counts as its workout."""
        return self.moving_minutes >= WALK_MIN_MOVING_MINUTES

    def message(self) -> str:
        """The verification line, in the RunnerUp verifier's own style."""
        return (
            f"Walking: {self.legs} walk(s), {self.distance_km:.1f} km, "
            f"{self.moving_minutes:.0f} min moving"
        )


def walk_shortfall(day: WalkDay) -> str:
    """Why a day's walking did not count yet."""
    return f"{day.message()} -- need {WALK_MIN_MOVING_MINUTES}+ min moving"


def walk_day(walks: Iterable[dict[str, Any]]) -> WalkDay:
    """Sum parsed walk exports (``_parse_tcx`` dicts) into one :class:`WalkDay`."""
    unique: dict[str, dict[str, Any]] = {}
    for walk in walks:
        unique.setdefault(str(walk.get("activity_id") or id(walk)), walk)
    ordered = sorted(unique.values(), key=lambda w: w.get("ended_at") or 0.0)
    moving = 0.0
    completed_at: float | None = None
    for walk in ordered:
        moving += float(walk.get("moving_seconds", 0.0))
        if completed_at is None and moving / 60 >= WALK_MIN_MOVING_MINUTES:
            completed_at = walk.get("ended_at")
    return WalkDay(
        legs=len(ordered),
        moving_minutes=moving / 60,
        distance_km=sum(float(w.get("distance_m", 0.0)) for w in ordered) / 1000,
        completed_at=completed_at,
    )
