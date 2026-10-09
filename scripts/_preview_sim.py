"""Simulation doubles for ``preview_shutdown.py``: real code, temporary state.

Split out to keep the script under the 250-line cap. Every class here runs
the production methods it inherits; only the I/O edges (the drop directory,
adb, the sudo-written config, the sick history) point at a temporary place.
"""

from __future__ import annotations

from datetime import date, datetime, time
import json
from typing import TYPE_CHECKING

import earned_time

from screen_locker import _grace_floor, _sick_tracker
from screen_locker._earned import first_minutes
from screen_locker._runnerup_verification import RunnerUpVerificationMixin
from screen_locker._shutdown import ShutdownMixin

if TYPE_CHECKING:
    from pathlib import Path

_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
HELPER_CEILING = 23 * 60  # adjust_shutdown_schedule.sh's RESTORE_CEILING


def stamp(day: date, hhmm_text: str) -> float:
    """Unix time of ``HH:MM`` local on ``day``."""
    hours, _, minutes = hhmm_text.partition(":")
    moment = datetime.combine(day, time(int(hours), int(minutes))).astimezone()
    return moment.timestamp()


def _iso(stamp: float) -> str:
    return datetime.fromtimestamp(stamp).astimezone().isoformat()


def write_walk(folder: Path, day: date, start: str, minutes: int) -> None:
    """A RunnerUp-style walk export: Sport="Other", the sport in the name."""
    begin = stamp(day, start)
    points = "".join(
        f"<Trackpoint><Time>{_iso(begin + s)}</Time>"
        f"<DistanceMeters>{s * 1.3:.1f}</DistanceMeters></Trackpoint>"
        for s in range(0, minutes * 60 + 1, 5)
    )
    stem = f"RunnerUp_Pixel_6a_{day}-{start.replace(':', '-')}-00_Walking.tcx"
    (folder / stem).write_text(
        f'<TrainingCenterDatabase xmlns="{_NS}"><Activities><Activity Sport="Other">'
        f"<Id>{day}T{start}:00Z</Id><Lap><TotalTimeSeconds>{minutes * 60}"
        f"</TotalTimeSeconds><DistanceMeters>{minutes * 78}</DistanceMeters>"
        f"<Track>{points}</Track></Lap></Activity></Activities></TrainingCenterDatabase>",
        encoding="utf-8",
    )


class SimRunnerUp(RunnerUpVerificationMixin):
    """The real backfill, reading only a temporary drop directory."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def _has_adb_device(self) -> bool:
        return False

    def fill(self, day: str, log: Path) -> bool:
        """The real RunnerUp backfill for ``day`` into ``log``."""
        return self._try_fill_runnerup_for_date(day, log)

    def _find_runnerup_exports_for_date(self, date_str: str) -> list[str]:
        return sorted(str(p) for p in self.folder.glob(f"*{date_str}*.tcx"))


class SimShutdown(ShutdownMixin):
    """The real add/absorb paths against an in-memory config."""

    def __init__(self, minutes: int) -> None:
        self.config = (minutes, minutes, 5 * 60)

    def _read_shutdown_config(self) -> tuple[int, int, int] | None:
        return self.config

    def _write_shutdown_config(
        self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = False
    ) -> bool:
        del restore
        clamp = min(HELPER_CEILING, mon_wed), min(HELPER_CEILING, thu_sun)
        self.config = (*clamp, morning_end)
        return True

    def credit(self, name: str, day: date, first_done: float) -> None:
        """One live pass: the earner's add (lift-absorbing), then the floor."""
        if name == earned_time.WORKOUT.name:
            self._adjust_shutdown_time_later()
        else:
            self._adjust_shutdown_time_by(first_minutes(earned_time.earner(name), day))
        self._apply_grace_floor(None, first_done=first_done)


def sick_history(day: date, tmp: Path, *, sick_day: bool) -> bool:
    """A temp sick history naming ``day``, read back through the real check."""
    history = tmp / "sick_history.json"
    history.write_text(json.dumps({"sick_days": [day.isoformat()] if sick_day else []}))
    vars(_sick_tracker)["SICK_HISTORY_FILE"] = history
    return _grace_floor.sick_on(day)
