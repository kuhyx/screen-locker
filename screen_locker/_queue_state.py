"""Publish the locker's gatelock queue wait so it is visible from outside.

A locker run that has decided to lock but is waiting for a higher-ranked
holder (``wake_alarm``) to release the screen looks, from any other process,
exactly like a hung one: the unit is ``active``, no window is up, and nothing
is written anywhere. On 2026-08-30 that state lasted 2h58m and the status
page still read a bare "Lock would fire", which is what sent the
investigation to the heat check instead.

The blocked run cannot answer questions about itself, so it writes this file
before it starts waiting and removes it when it stops. Readers (the web
status payload) treat its absence as "not queued".
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any

from screen_locker._constants import QUEUE_STATE_FILE

_logger = logging.getLogger(__name__)


def publish_queue_wait(blocked_by: tuple[str, ...], elapsed_seconds: float) -> None:
    """Record that this run is queued behind *blocked_by*, or no longer is.

    Args:
        blocked_by: Apps holding the screen ahead of us; empty means clear.
        elapsed_seconds: How long the wait has lasted so far.
    """
    if not blocked_by:
        clear_queue_wait()
        return
    record = {
        "blocked_by": list(blocked_by),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "updated": datetime.now(tz=UTC).isoformat(),
    }
    try:
        QUEUE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUEUE_STATE_FILE.write_text(json.dumps(record), encoding="utf-8")
    except OSError as exc:
        _logger.warning(
            "Could not publish the queue wait to %s (%s) — the status page "
            "will show this run as simply 'would lock' while it is in fact "
            "blocked behind %s",
            QUEUE_STATE_FILE,
            exc,
            ", ".join(blocked_by),
        )


def clear_queue_wait() -> None:
    """Remove the published wait, so readers stop reporting one."""
    try:
        QUEUE_STATE_FILE.unlink(missing_ok=True)
    except OSError as exc:
        _logger.warning(
            "Could not clear the queue wait at %s (%s) — the status page may "
            "keep claiming this run is queued after it has armed",
            QUEUE_STATE_FILE,
            exc,
        )


def read_queue_wait() -> dict[str, Any] | None:
    """Return the currently published wait, or None when there is none.

    Returns:
        The published record, or None when nothing is queued or the file
        could not be read.
    """
    # Absence is the normal case (nothing is queued), so it is tested for
    # rather than caught -- an `except FileNotFoundError: return None` here
    # would be indistinguishable from swallowing a real read failure.
    if not QUEUE_STATE_FILE.exists():
        return None
    try:
        raw = QUEUE_STATE_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.warning(
            "Could not read the queue wait at %s (%s) — reporting 'not "
            "queued', which may be wrong",
            QUEUE_STATE_FILE,
            exc,
        )
        return None
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        _logger.warning(
            "Queue wait at %s is unparsable (%s) — reporting 'not queued'",
            QUEUE_STATE_FILE,
            exc,
        )
        return None
    if not isinstance(record, dict):
        _logger.warning(
            "Queue wait at %s is not an object — reporting 'not queued'",
            QUEUE_STATE_FILE,
        )
        return None
    return record
