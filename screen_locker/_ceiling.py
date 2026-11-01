"""The latest shutdown a day can earn: ``earned_time``'s ceiling, bounded at 23:00."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import earned_time

if TYPE_CHECKING:
    from datetime import date

_logger = logging.getLogger(__name__)

# adjust_shutdown_schedule.sh's RESTORE_CEILING (23:00): the hard upper bound
# every --restore write is clamped to, and the answer when the lookup fails.
HARD_CEILING_MINUTES = 23 * 60


def ceiling(day: date) -> int:
    """The latest shutdown ``day`` can earn, minutes after its midnight.

    Never above :data:`HARD_CEILING_MINUTES`. A lookup that raises fails open
    to that bound -- the same cap the helper enforces anyway -- and says so at
    warning, so a broken registry cannot silently lift or lower the cap.
    """
    fn = getattr(earned_time, "shutdown_ceiling_for", None)
    if fn is None:
        return min(HARD_CEILING_MINUTES, int(earned_time.SHUTDOWN_CEILING_MINUTES))
    try:
        return min(HARD_CEILING_MINUTES, int(fn(day)))
    except (ArithmeticError, LookupError, TypeError, ValueError) as err:
        _logger.warning(
            "shutdown ceiling for %s unavailable (%s); using %s",
            day,
            err,
            f"{HARD_CEILING_MINUTES // 60:02d}:{HARD_CEILING_MINUTES % 60:02d}",
        )
        return HARD_CEILING_MINUTES
