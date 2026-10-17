"""The workout lock does not re-arm after tonight's evening night-lockdown.

The predicate itself is ``gatelock.night_lockdown``, shared with
leetcode-guard and book-guard (diet-guard deliberately does not opt in); this
module only binds screen-locker's path, which the test suite redirects, and
the ladder rung that honours it.

Why: once tonight's lockdown has fired, a late credit (``_late_credit``) can
lift it -- and re-locking behind the workout gate the same evening would make
a finished workout impossible to submit. Only an EVENING lock counts (local
date today, >= 12:00); the 04:01 morning re-lock does not. Missing or garbage
stamp means "no lockdown": the workout lock behaves exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatelock.night_lockdown import (
    NIGHT_LOCKDOWN_STAMP as _SHARED_STAMP,
)
from gatelock.night_lockdown import (
    evening_lockdown_today,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

__all__ = [
    "EVENING_LOCKDOWN_REASON",
    "NIGHT_LOCKDOWN_STAMP",
    "has_evening_lockdown_today",
    "skip_after_evening_lockdown",
    "tonights_lockdown",
]

NIGHT_LOCKDOWN_STAMP: Path = _SHARED_STAMP

EVENING_LOCKDOWN_REASON = "evening_lockdown_today"


def tonights_lockdown(now: datetime | None = None) -> datetime | None:
    """When tonight's evening lockdown locked, or None if it has not yet."""
    return evening_lockdown_today(NIGHT_LOCKDOWN_STAMP, now)


def has_evening_lockdown_today() -> bool:
    """Whether tonight's evening lockdown already happened. Read-only."""
    return tonights_lockdown() is not None


def skip_after_evening_lockdown(record_skip: Callable[..., None]) -> bool:
    """Skip enforcement once tonight's evening lockdown has fired.

    Takes the locker's ``_record_skip`` (which exits the process) rather than
    the locker, like ``_lock_invariant``. Returns True when the skip was
    recorded, False when the lock may go ahead.
    """
    locked_at = tonights_lockdown()
    if locked_at is None:
        return False
    record_skip(
        EVENING_LOCKDOWN_REASON,
        f"Tonight's night lockdown already locked at {locked_at:%H:%M}; the "
        "workout lock does not re-arm after it.",
        locked_at=locked_at.isoformat(),
    )
    return True
