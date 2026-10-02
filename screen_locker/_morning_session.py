"""Read the morning-session carrot the wake-alarm service signed for today.

The reader itself is ``gatelock.morning_session``, shared with leetcode-guard
and book-guard; this module only binds screen-locker's path and retry budget,
which the test suite redirects. The policy lives in wake-alarm: the only
decision anywhere is *HMAC ok, dated today, now < exempt_until*.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from gatelock.morning_session import (
    MORNING_RETRY_SECONDS as _SHARED_RETRY_SECONDS,
)
from gatelock.morning_session import (
    MorningSkip,
    morning_skip,
)

from screen_locker._constants import MORNING_SESSION_FILE

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

__all__ = ["MorningSkip", "has_workout_skip_today", "morning_skip_today"]

MORNING_RETRY_SECONDS: float = _SHARED_RETRY_SECONDS


def morning_skip_today(
    now: datetime | None = None,
    *,
    wait: bool,
    sleep: Callable[[float], None] = time.sleep,
) -> MorningSkip | None:
    """The skip the morning session earned, or None.

    With ``wait`` (the enforce path only), a file that is not today's during
    the morning window is retried so a freshly booted PC gives wake-alarm's
    catch-up run a chance to land.
    """
    return morning_skip(
        MORNING_SESSION_FILE,
        now,
        wait=wait,
        retry_seconds=MORNING_RETRY_SECONDS,
        sleep=sleep,
    )


def has_workout_skip_today() -> bool:
    """Whether the morning session earned a skip right now. Never waits."""
    return morning_skip_today(wait=False) is not None
