"""Sick-day shutdown, applied live: 20:00 plus the day's gaming pay.

The daily reset already resolves a sick day with ``earned_time.resolve(...,
sick=True)``. But a day is usually marked sick *after* that reset ran --
at 10:00 from the lock screen or the phone -- and the reset is stamped once
per day. This pass closes the gap: on every 5-minute locker tick, every
``--sync-only`` / ``--apply-bonuses`` pass and right after the lock screen's
"I'm sick" tap, it raises tonight's shutdown to the derived sick target
(:func:`sick_target`: 20:00 plus every credit's gaming pay, earned_time 0.13.0).

Credits stack on 20:00 (kuhy, 2026-10-17: LeetCode + reading is 22:00, not
the 20:10 that 0.11.0's non-stacking floor gave). The target is absolute,
re-derived from the ledgers, so on a sick day a live credit raises to it
instead of adding (``ShutdownMixin``): the new row is already in the sum.
No lift is recorded, so nothing is absorbed.

Raise-only. Un-marking today does not lower the config until the next
daily reset re-derives it.
"""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING

from screen_locker._bonus_lock import bonus_lock
from screen_locker._constants import GRACE_STATE_FILE
from screen_locker._day import today_str
from screen_locker._earned import hhmm
from screen_locker._grace_floor import save_lift, tonight_minutes
from screen_locker._shutdown_target import gather
from screen_locker._sick import is_sick

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


def sick_target(day: date, log_file: Path | None) -> int:
    """Tonight's sick-day shutdown, re-derived from the ledgers and the log."""
    return gather(day, log_file).minutes


class SickFloorMixin:
    """Lifts tonight's shutdown to the sick floor; composed into ShutdownMixin."""

    if TYPE_CHECKING:

        def _read_shutdown_config(self) -> tuple[int, int, int] | None: ...

        def _write_shutdown_config(
            self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = ...
        ) -> bool: ...

    def _apply_sick_floor(self) -> bool:
        """Raise tonight's shutdown to the sick target if today is sick.

        Returns True when the config was raised on this call.
        """
        today = today_str()
        day = date.fromisoformat(today)
        if not is_sick(day):
            return False
        with bonus_lock(GRACE_STATE_FILE):
            config = self._read_shutdown_config()
            if config is None:
                _logger.warning("Sick floor: shutdown config unreadable; not applied")
                return False
            current = tonight_minutes(config, day)
            floor = sick_target(day, getattr(self, "log_file", None))
            if floor <= current:
                return False
            mon_wed, thu_sun, morning = config
            if not self._write_shutdown_config(
                max(mon_wed, floor), max(thu_sun, floor), morning, restore=True
            ):
                _logger.warning("Sick floor: failed to write shutdown config")
                return False
            save_lift(0, GRACE_STATE_FILE)  # stacked: nothing to absorb
        _logger.info(
            "Sick floor: shutdown %s -> %s (sick day).", hhmm(current), hhmm(floor)
        )
        return True
