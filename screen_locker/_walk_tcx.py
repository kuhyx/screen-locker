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
real lap reads 101 min for 1 km of standing about. The track is cut into
windows of at least ``TRACK_WINDOW_SECONDS`` (a fix every second jitters, so
one raw pair can read 15 m/s inside a 3 m/s run) and each window is judged by
its average speed. Faster than ``MAX_MOVING_SPEED_MPS`` (25 km/h) is a vehicle
or a GPS jump: neither time nor distance counts, so a bus ride earns nothing.
Otherwise its metres count, and its seconds count as moving time at
``MIN_MOVING_SPEED_MPS`` or faster; standing still is too slow. A window longer
than ``WALK_MAX_GAP_SECONDS`` is a signal dropout (real exports have 2 minute
ones): the runner may have kept running unseen, so it counts as moving only at
``MIN_DROPOUT_SPEED_MPS`` or faster, while a pause (no distance across the
gap) earns nothing -- a pause cannot buy a run its duration.
The day's distance is the sum of the windows (``track_distance_m``), never the
lap's ``DistanceMeters`` total, and an export with no trackpoints cannot be
speed-checked, so it credits nothing. Only the root-DB fallback, which has no
trackpoints at all, is judged by its recorded distance and duration.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from screen_locker._activity_day import (
    SPORT_NAMES,
    ActivityDay,
    activity_day,
    activity_shortfall,
    distance_qualifies,
    moving_qualifies,
)
from screen_locker._constants import (
    MAX_MOVING_SPEED_MPS,
    MIN_DROPOUT_SPEED_MPS,
    MIN_MOVING_SPEED_MPS,
    TRACK_WINDOW_SECONDS,
    WALK_MAX_GAP_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
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


def _segments(
    points: list[tuple[float, float]],
) -> Iterator[tuple[float, float]]:
    """``(seconds, metres)`` of the track cut into windows of >= TRACK_WINDOW_SECONDS.

    A fix every second jitters (one pair can read 15 m/s inside a 3 m/s run),
    so speed is judged over a window, never over a raw 1 s pair. Fixes that
    are already further apart than the window are their own segment.
    """
    if not points:
        return
    anchor = points[0]
    for point in points[1:]:
        if point[0] - anchor[0] >= TRACK_WINDOW_SECONDS:
            yield point[0] - anchor[0], point[1] - anchor[1]
            anchor = point
    if points[-1] is not anchor:
        yield points[-1][0] - anchor[0], points[-1][1] - anchor[1]


def track_summary(activity: ET.Element) -> dict[str, Any]:
    """Moving seconds, credited distance and end time, from the trackpoints.

    A segment (see :func:`_segments`) counts unless it was travelled faster
    than ``MAX_MOVING_SPEED_MPS``: it then adds its metres to
    ``track_distance_m``, and its seconds to ``moving_seconds`` too when it was
    travelled at least at ``MIN_MOVING_SPEED_MPS``. A segment longer than
    ``WALK_MAX_GAP_SECONDS`` is a signal dropout whose motion is unknown; it
    only counts as moving time at ``MIN_DROPOUT_SPEED_MPS``, so a pause (no
    distance across the gap) earns no time while a runner whose GPS went away
    for two minutes keeps the time and metres the far side proves.
    """
    points = _trackpoints(activity)
    moving = 0.0
    metres = 0.0
    for seconds, travelled in _segments(points):
        if seconds <= 0:
            continue
        speed = travelled / seconds
        if speed > MAX_MOVING_SPEED_MPS:
            continue
        metres += max(travelled, 0.0)
        floor = (
            MIN_MOVING_SPEED_MPS
            if seconds <= WALK_MAX_GAP_SECONDS
            else MIN_DROPOUT_SPEED_MPS
        )
        if speed >= floor:
            moving += seconds
    return {
        "activity_id": activity.findtext(f"{_TCX_NS}Id") or "",
        "moving_seconds": moving,
        "track_distance_m": metres,
        "ended_at": points[-1][0] if points else None,
    }


# The day aggregate lives in ``_activity_day``; these names stay importable here,
# along with the walk-only names they replaced.
WalkDay = ActivityDay
walk_day = activity_day
walk_shortfall = activity_shortfall
__all__ = [
    "SPORT_NAMES",
    "ActivityDay",
    "WalkDay",
    "activity_day",
    "activity_shortfall",
    "distance_qualifies",
    "is_walking_export",
    "moving_qualifies",
    "track_summary",
    "walk_day",
    "walk_shortfall",
]
