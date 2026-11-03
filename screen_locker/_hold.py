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
    from tkinter import Misc

__all__ = ["HOLD_REASON", "skip_during_hold", "watch_for_hold", "workout_hold_active"]

_logger = logging.getLogger(__name__)

HOLD_REASON = "test_hold_active"
_GATE = "workout"
# Well inside the 60 s a hold may take to lift an open window.
POLL_MS = 30_000


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


def watch_for_hold(root: Misc, close: Callable[[], None]) -> None:
    """Close an already-open window within one poll of a hold starting.

    ``close`` is the locker's own ``close`` -- it tears the window down and
    exits 0 without writing a credit or a penalty, so a hold that interrupts
    an open prompt/lock changes nothing but the screen. Polls on the Tk loop
    (no thread) and stops re-arming once it fires.
    """

    def _tick() -> None:
        if workout_hold_active():
            _logger.warning(
                "A test hold started while the workout window was open — "
                "closing it without credit or penalty."
            )
            close()
            return
        root.after(POLL_MS, _tick)

    root.after(POLL_MS, _tick)
