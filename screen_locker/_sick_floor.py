"""Sick-day shutdown floor, applied live: 20:00 the moment today turns sick.

The daily reset already resolves a sick day with ``earned_time.resolve(...,
sick=True)``. But a day is usually marked sick *after* that reset ran --
at 10:00 from the lock screen or the phone -- and the reset is stamped once
per day. This pass closes the gap: on every 5-minute locker tick, every
``--sync-only`` / ``--apply-bonuses`` pass and right after the lock screen's
"I'm sick" tap, it lifts tonight's shutdown to
``earned_time.sick_shutdown_minutes`` (``max(20:00, current)``, capped at the
day's ceiling).

The lift is a floor, not a bonus, exactly like the grace floor: it is added
to the same ``grace_floor.json`` lift, so a workout credited later is paid
out of it first (``_grace_floor.plan_absorb``) and lands on
``max(20:00, ladder)`` -- 20:40, not 20:00 + the workout's whole reward.

Raise-only. Un-marking today does not lower the config until the next
daily reset re-derives it.
"""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING

import earned_time

from screen_locker._bonus_lock import bonus_lock
from screen_locker._constants import GRACE_STATE_FILE
from screen_locker._day import today_str
from screen_locker._earned import hhmm
from screen_locker._grace_floor import load_lift, save_lift, tonight_minutes
from screen_locker._sick import is_sick

_logger = logging.getLogger(__name__)


class SickFloorMixin:
    """Lifts tonight's shutdown to the sick floor; composed into ShutdownMixin."""

    if TYPE_CHECKING:

        def _read_shutdown_config(self) -> tuple[int, int, int] | None: ...

        def _write_shutdown_config(
            self, mon_wed: int, thu_sun: int, morning_end: int, *, restore: bool = ...
        ) -> bool: ...

    def _apply_sick_floor(self) -> bool:
        """Raise tonight's shutdown to the sick floor if today is sick.

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
            floor = earned_time.sick_shutdown_minutes(current, day)
            if floor <= current:
                return False
            mon_wed, thu_sun, morning = config
            if not self._write_shutdown_config(
                max(mon_wed, floor), max(thu_sun, floor), morning, restore=True
            ):
                _logger.warning("Sick floor: failed to write shutdown config")
                return False
            lift = load_lift(GRACE_STATE_FILE, today) + floor - current
            save_lift(lift, GRACE_STATE_FILE)
        _logger.info(
            "Sick floor: shutdown %s -> %s (sick day).", hhmm(current), hhmm(floor)
        )
        return True
