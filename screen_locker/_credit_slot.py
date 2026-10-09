"""Which credit a newly written workout earns, decided by slot like the reset.

The live credit path used to ask "was any counted workout already logged
today?" -- so the two StrongLifts ingestion paths of ONE session
(``pc_workout_verified`` from the session sync, ``phone_verified`` from the
early-bird auto-upgrade) earned the first-unit +2h and then a further-unit +1h
(2026-10-09; also 07-17 and 07-27 in ``duplicate_credits.json``). The daily
reset counts the same day with :func:`~screen_locker._weekly_check.count_day_credits`,
which collapses them onto one slot. Deciding the live credit with that same
counter makes the two agree by construction.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import enum
import logging
from typing import TYPE_CHECKING, Any, Final

from screen_locker._bonus_lock import bonus_lock
from screen_locker._weekly_check import count_day_credits

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

# count_day_credits only uses the date to build slot keys, and both counts
# below are taken over the same day, so any fixed label is equivalent.
_SAME_DAY: Final = "day"


class CreditSlot(enum.Enum):
    """What the newest entry of a day earns."""

    NONE = "earns no credit (not a counted workout type)"
    FIRST = "first credit slot of the day"
    FURTHER = "a new, distinct credit slot after the first"
    OCCUPIED = "a slot an earlier entry of the day already credited"


def credit_slot(
    prior_entries: list[dict[str, Any]], workout_data: Mapping[str, Any]
) -> CreditSlot:
    """Classify ``workout_data`` against the day's entries written before it.

    Args:
        prior_entries: The day's log entries before the new one, as returned
            by the write chokepoint (snapshotted under the log lock).
        workout_data: The new entry's ``workout_data``.
    """
    new_entry = {"workout_data": dict(workout_data)}
    day = [e for e in prior_entries if isinstance(e, dict)]
    before = count_day_credits(_SAME_DAY, day)
    with_new = count_day_credits(_SAME_DAY, [*day, new_entry])
    if with_new == before:
        # No new slot: either it earns nothing at all, or its slot is taken.
        return CreditSlot.OCCUPIED if _counts_alone(new_entry) else CreditSlot.NONE
    return CreditSlot.FIRST if before == 0 else CreditSlot.FURTHER


def _counts_alone(entry: Mapping[str, Any]) -> bool:
    """Whether ``entry`` would earn a credit on an otherwise empty day."""
    return count_day_credits(_SAME_DAY, [entry]) == 1


@contextmanager
def locked_shutdown_state(state_file: Path) -> Iterator[None]:
    """Hold :func:`bonus_lock` on ``state_file``; on failure, warn and go on.

    The reset and the flat-bonus pass hold the same lock, so a credit can no
    longer lose its minutes to their read-add-write. Never nest inside them:
    a second flock on a new fd in the same process deadlocks.
    """
    with ExitStack() as stack:
        try:
            stack.enter_context(bonus_lock(state_file))
        except OSError as exc:
            _logger.warning(
                "Could not lock %s (%s) — applying the workout credit without "
                "it; a reset running at the same moment could overwrite it",
                state_file,
                exc,
            )
        yield
