"""Simulation doubles for ``preview_shutdown.py``: real code, temporary state.

Split out to keep the script under the 250-line cap. Every class here runs
the production methods it inherits; only the I/O edges (the drop directory,
adb, the sudo-written config, the sickdays pool) point at a temporary place.
"""

from __future__ import annotations

from datetime import date, datetime, time
import sys
from typing import TYPE_CHECKING

import earned_time
import sickdays

from screen_locker._earned import first_minutes
from screen_locker._runnerup_verification import RunnerUpVerificationMixin
from screen_locker._shutdown import ShutdownMixin
from screen_locker._sick import is_sick

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

    def credit(self, name: str, day: date, at: float | None = None) -> None:
        """One live pass: the earner's add (lift-absorbing), then the floors.

        ``sick`` is not an earner: it marks the (temporary) pool and runs the
        live sick-floor pass, as the lock screen's button and the 5-minute
        tick do.
        """
        if name == SICK_STEP:
            sick_pool(day, sick_day=True)
        elif name == earned_time.WORKOUT.name:
            self._adjust_shutdown_time_later(at=at)
        else:
            minutes = first_minutes(earned_time.earner(name), day)
            self._adjust_shutdown_time_by(minutes, at=at)
        self._apply_sick_floor()


# The --sequence step that marks the day sick instead of crediting an earner.
SICK_STEP = "sick"


def use_temp_pool(tmp: Path) -> None:
    """Point every sickdays read and write at a pool under ``tmp``."""
    pool = sickdays.Paths.under(tmp / "sickdays")
    # Every sickdays module that bound ``resolve_paths`` by name: ``_api`` (the
    # reads, ``stands_down`` included) and the writers (``_keep_api``, ...).
    for name, module in tuple(sys.modules.items()):
        if name.startswith("sickdays.") and "resolve_paths" in vars(module):
            vars(module)["resolve_paths"] = lambda paths: paths or pool


def sick_pool(day: date, *, sick_day: bool) -> bool:
    """Mark ``day`` sick in the temp pool, read back through the real check.

    Call :func:`use_temp_pool` first: this writes through sickdays' own
    ``add_sick_day``, with ``day`` as "today" and no free-day check.
    """
    if sick_day and not is_sick(day):
        sickdays.add_sick_day(day, is_free=lambda _day: False, now=day)
    return is_sick(day)
