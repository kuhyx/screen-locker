"""A credit at or after tonight's shutdown counts from its own time.

Shutting down must never make a finished task impossible to submit (kuhy,
2026-10-17). The config is read-add-write, so a credit landing after the
shutdown used to add its minutes to a time already past: LeetCode at 19:00
after an 18:00 shutdown made 19:00, and the machine stayed locked. Now such
a credit moves tonight to ``its own time + its reward``, capped at the
ceiling -- only the ceiling (23:00) is hard.

The anchor is the credit's own time (a run's end, a ledger row's), never the
moment a sync applied it, so a late upload does not buy extra time. Past the
shutdown the grace and sick lifts are spent: the caller clears the lift.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import time
from typing import TYPE_CHECKING

from screen_locker._day import today_str
from screen_locker._earned import ceiling, hhmm
from screen_locker._grace_floor import save_lift, tonight_minutes

_logger = logging.getLogger(__name__)


def _now() -> float:
    """The clock a credit without its own time is stamped with."""
    return time.time()


def late_tonight(
    config: tuple[int, int, int], day: date, at: float, minutes: int
) -> int | None:
    """Tonight's new shutdown for a late credit, or ``None`` if it is not late.

    Late means timed on ``day`` at or after tonight's shutdown: the check
    script locks at ``now >= shutdown``, so a credit exactly on it is late.
    """
    moment = datetime.fromtimestamp(at).astimezone()
    if moment.date() != day:
        return None
    done = moment.hour * 60 + moment.minute
    if done < tonight_minutes(config, day):
        return None
    return min(ceiling(day), done + minutes)


class LateCreditMixin:
    """Late credits and sick-day credits; composed into ShutdownMixin."""

    if TYPE_CHECKING:

        def _read_shutdown_config(self) -> tuple[int, int, int] | None: ...

        def _write_shutdown_config(
            self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = ...
        ) -> bool: ...

        def _apply_sick_floor(self) -> bool: ...

    def _raise_on_sick_day(self, minutes: int, at: float | None) -> bool:
        """A sick day's credit: raise to the derived target, never add.

        The credit's row is already in the target (``_sick_floor``), so adding
        its minutes on top would pay it twice; a late one still counts from
        its own time. True even when nothing moved (capped, or already there):
        the credit is accounted for, and a failed write is retried by the next
        tick's sick pass.
        """
        self._apply_sick_floor()
        late = self._late_write(minutes, at)
        return True if late is None else late

    def _late_write(self, minutes: int, at: float | None) -> bool | None:
        """Write a late credit's shutdown; ``None`` when it is not late."""
        day = date.fromisoformat(today_str())
        try:
            config = self._read_shutdown_config()
        except (OSError, ValueError) as exc:
            # The add path reads it again inside its own guard and fails there.
            _logger.warning("Late credit: cannot read shutdown config (%s)", exc)
            return None
        if config is None:
            return None  # the add path reads it again and reports it
        target = late_tonight(config, day, _now() if at is None else at, minutes)
        if target is None:
            return None
        mon_wed, thu_sun, morning = config
        if not self._write_shutdown_config(
            max(mon_wed, target), max(thu_sun, target), morning, restore=True
        ):
            _logger.warning("Late credit: failed to write shutdown config")
            return False
        save_lift(0)  # past the shutdown, the floors' lift is spent
        _logger.info(
            "Late credit: shutdown %s -> %s (earned at or after tonight's).",
            hhmm(tonight_minutes(config, day)),
            hhmm(target),
        )
        return True
