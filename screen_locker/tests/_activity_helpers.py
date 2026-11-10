"""Helpers for the unified-activity tests: TCX builder and a phone-less verifier."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._runnerup_verification import RunnerUpVerificationMixin

if TYPE_CHECKING:
    from pathlib import Path

_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
DAY = "2026-10-10"


def tcx(
    sport: str,
    start: str,
    *,
    moving_min: float,
    metres: float,
    pause_min: float = 0.0,
) -> str:
    """A RunnerUp-shaped export: ``moving_min`` of steady motion covering ``metres``.

    A ``pause_min`` pause sits in the middle of the track as ONE gap between
    two trackpoints (the clock runs, the distance does not), so the lap's
    wall-clock time is ``moving_min + pause_min``.
    """
    begin = datetime.fromisoformat(f"{DAY}T{start}:00+00:00")
    speed = metres / (moving_min * 60)
    total = int(moving_min * 60)
    half = total // 2 // 5 * 5
    pause = int(pause_min * 60)
    points = ""
    for s in range(0, total + 1, 5):
        offset = s + (pause if s > half else 0)
        points += (
            f"<Trackpoint><Time>{(begin + timedelta(seconds=offset)).isoformat()}"
            f"</Time><DistanceMeters>{s * speed:.1f}</DistanceMeters></Trackpoint>"
        )
    return (
        f'<TrainingCenterDatabase xmlns="{_NS}"><Activities>'
        f'<Activity Sport="{sport}"><Id>{DAY}T{start}</Id><Lap>'
        f"<TotalTimeSeconds>{total + pause}</TotalTimeSeconds>"
        f"<DistanceMeters>{metres}</DistanceMeters>"
        f"<Track>{points}</Track></Lap></Activity></Activities>"
        "</TrainingCenterDatabase>"
    )


class Verifier(RunnerUpVerificationMixin):
    """The real mixin reading one temporary drop directory and no phone."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def _has_adb_device(self) -> bool:
        return False

    def _run_adb(self, args: list[str]) -> tuple[bool, str]:
        return False, ""

    def _find_runnerup_exports_for_date(self, date_str: str) -> list[str]:
        return sorted(str(p) for p in self.folder.glob(f"*{date_str}*.tcx"))


def drop(folder: Path, stamp: str, suffix: str, body: str) -> None:
    """Write a RunnerUp-named export for the test day."""
    (folder / f"RunnerUp_Pixel_6a_{DAY}-{stamp}{suffix}.tcx").write_text(body)


def verify(verifier: Verifier) -> tuple[str, str] | None:
    """The file-based verdict for the test day."""
    with patch("screen_locker._runnerup_verification.today_str", return_value=DAY):
        return verifier._verify_runnerup_via_files()


def tcx_points(sport: str, start: str, points: list[tuple[int, float]]) -> str:
    """An export whose track is exactly ``(seconds after start, cumulative metres)``."""
    begin = datetime.fromisoformat(f"{DAY}T{start}:00+00:00")
    body = "".join(
        f"<Trackpoint><Time>{(begin + timedelta(seconds=s)).isoformat()}</Time>"
        f"<DistanceMeters>{m:.1f}</DistanceMeters></Trackpoint>"
        for s, m in points
    )
    return (
        f'<TrainingCenterDatabase xmlns="{_NS}"><Activities>'
        f'<Activity Sport="{sport}"><Id>{DAY}T{start}</Id><Lap>'
        f"<TotalTimeSeconds>{points[-1][0]}</TotalTimeSeconds>"
        f"<DistanceMeters>{points[-1][1]}</DistanceMeters>"
        f"<Track>{body}</Track></Lap></Activity></Activities>"
        "</TrainingCenterDatabase>"
    )
