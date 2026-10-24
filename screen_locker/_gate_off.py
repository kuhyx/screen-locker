"""Whether an earner's gate stands down today, asked live (earned_time 0.18.0).

Only LeetCode has a price: while its gate is on, earned_time pays only the
signed charge that covers the whole day, never one solve of five (kuhy,
2026-10-24). A free day or a sick day not keeping ``leetcode`` has no price,
so one verified solve earns. Never stored: clearing the sick day takes the
exception back on the next read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import earned_time
import freedays
import sickdays

from screen_locker._sick import stands_down

if TYPE_CHECKING:
    from datetime import date


def gate_off(earner: earned_time.Earner, day: date) -> bool:
    """Whether ``earner``'s gate is off on ``day`` (always False but LeetCode)."""
    if earner.name != earned_time.LEETCODE.name:
        return False
    return freedays.is_free_day(day) or stands_down(sickdays.LOCKER_LEETCODE, day)
