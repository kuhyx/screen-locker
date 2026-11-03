"""A declared test hold keeps the workout locker from showing any window.

``holds`` (kuhyx/utils, ``holds-v0.1.0``) is the shared "a proctored test is
running, leave the PC usable" switch. Every workout-locker path -- the relaxed
day's optional prompt, the strict lock and the early-bird re-check -- runs
through ``_startup_checks._check_non_verify_exits``, so one rung there covers
them all. It sits BELOW the reset/bonus/ingest/early-bird bookkeeping: a hold
only suppresses the window, never a credit or a penalty term.

Fail closed: if ``holds`` cannot be imported or read, there is no hold and the
locker behaves exactly as it did before, with an ERROR in the journal. A hold
that fails open would be a free escape from the gate.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

__all__ = ["HOLD_REASON", "skip_during_hold", "workout_hold_active"]

_logger = logging.getLogger(__name__)

HOLD_REASON = "test_hold_active"
_GATE = "workout"


def workout_hold_active(now: datetime | None = None) -> bool:
    """Whether a declared hold covers the workout gate right now."""
    try:
        # Imported at call time so a missing package fails closed, per call.
        holds = importlib.import_module("holds")
        return bool(holds.covers(_GATE, now))
    except ImportError, OSError, ValueError, TypeError, KeyError:
        _logger.exception(
            "Could not read the test holds — treating it as no hold, so "
            "the workout locker behaves as normal"
        )
        return False


def skip_during_hold(record_skip: Callable[..., None]) -> bool:
    """Skip enforcement while a hold is active.

    Takes the locker's ``_record_skip`` (which exits the process) rather than
    the locker, like ``_night_lockdown``. Returns True when the skip was
    recorded, False when the ladder may go on.
    """
    if not workout_hold_active():
        return False
    record_skip(
        HOLD_REASON,
        "A declared test hold is active — no workout prompt or lock window "
        "until it ends (credit and penalty bookkeeping already ran).",
    )
    return True
