"""Turning a completed push into an honest result.

Split out of :mod:`screen_locker._manual_push` to keep every file under the
250-line cap.

A push that the primary backend refused still reaches the GitHub mirror, and
the records are not lost -- the phone reads the union of both. What must not
happen is that half-landed push logging the same line as a whole one, which is
how weeks of broken Firebase pushes looked healthy in the journal.
"""

from __future__ import annotations

import logging

from screen_locker._constants import SYNC_REPO_NAME, SYNC_REPO_OWNER
from screen_locker._degraded_sources import degraded_sources

_logger = logging.getLogger(__name__)


def describe_push(record_count: int) -> tuple[bool, str]:
    """Report whether every backend received the records, and say so.

    Args:
        record_count: How many records the push carried.

    Returns:
        ``(complete, reason)`` -- ``reason`` reads like a sentence either way,
        because it is what ``PushResult`` carries back to the caller.
    """
    missing = [source.name for source in degraded_sources()]
    if not missing:
        _logger.info(
            "Synced %d workout(s) to %s/%s",
            record_count,
            SYNC_REPO_OWNER,
            SYNC_REPO_NAME,
        )
        return True, "pushed"
    names = ", ".join(missing)
    reason = (
        f"pushed to {SYNC_REPO_OWNER}/{SYNC_REPO_NAME} only; "
        f"{names} did NOT receive these records"
    )
    _logger.warning(
        "Workout sync push INCOMPLETE for %d workout(s): %s — the phone reads "
        "both backends, so this still syncs, but %s is broken and must be "
        "fixed before it is the only path left",
        record_count,
        reason,
        names,
    )
    return False, reason
