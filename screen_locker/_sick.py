"""The one place screen-locker asks the shared ``sickdays`` pool.

A sick day is a date in that pool, nothing else: no budget, no countdown, no
justification and no debt. Every consumer here (lock ladder, shutdown,
status, MCP) goes through this module, so the answer cannot drift between
them and tests have one seam.

Reading never raises: an unreadable pool is logged by ``sickdays`` and reads
as *not sick* -- fail closed, the locks apply.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
from typing import TYPE_CHECKING

import sickdays

if TYPE_CHECKING:
    from datetime import date

_logger = logging.getLogger(__name__)


def is_sick(day: date | None = None) -> bool:
    """Whether ``day`` (default: today) is a sick day."""
    return sickdays.is_sick_day(day)


def sick_dates() -> frozenset[date]:
    """Every date the pool marks sick, past and future."""
    return sickdays.sick_days()


def push_in_background() -> threading.Thread:
    """Start one best-effort ``sickdays.sync_quietly`` on a background thread.

    So the phone sees a lock-screen mark without waiting for the 15-minute
    sickdays-sync timer. Not a daemon: the lock window closes at once and the
    process lingers only until the push ends, instead of killing it mid-write.
    ``sync_quietly`` never raises; a failed push is retried by that timer.
    """
    worker = threading.Thread(
        target=sickdays.sync_quietly, name="sickdays-push", daemon=False
    )
    worker.start()
    return worker


@dataclass(frozen=True)
class MarkResult:
    """Outcome of :func:`mark_today_sick`.

    Attributes:
        ok: Today is a sick day now (newly marked or already was).
        message: What to show the user: a confirmation, or why it was refused.
    """

    ok: bool
    message: str


def mark_today_sick() -> MarkResult:
    """Mark today sick in the shared pool; every gate stands down for it.

    Already sick counts as success. Any other refusal (a free day, an
    unreadable pool, freedays not importable) is returned with sickdays' own
    explanation, so the lock screen can show it instead of unlocking.
    """
    today = sickdays.today()
    try:
        sickdays.add_sick_day(today)
    except sickdays.AlreadySickError:
        _logger.warning("%s was already a sick day; unlocking", today)
        return MarkResult(ok=True, message="Today is already a sick day.")
    except sickdays.SickDayError as exc:
        _logger.warning("Could not mark %s as a sick day: %s", today, exc)
        return MarkResult(ok=False, message=str(exc))
    _logger.warning("Marked %s as a sick day from the lock screen", today)
    return MarkResult(ok=True, message="Today is a sick day. Get well soon.")
