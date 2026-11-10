"""A day's activities summed under the one crediting rule (see ``_walk_tcx``).

The day counts as the workout once EITHER its summed distance reaches
``MIN_RUN_DISTANCE_KM`` (within the GPS tolerance) OR its summed moving time
reaches the shared duration bar. The sport only labels messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from screen_locker._constants import (
    MIN_RUN_DISTANCE_KM,
    MIN_WORKOUT_DURATION_MINUTES,
    RUNNERUP_DISTANCE_TOLERANCE,
    WORKOUT_DURATION_ACCEPT_MINUTES,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

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
