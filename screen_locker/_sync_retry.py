"""Bounded retry for sync calls that run before the network is up.

Every sync entry point here is reached from the morning routine, which systemd
starts immediately after boot and after resume — routinely a few seconds before
DHCP/DNS have settled. A single-shot call in that window fails for a reason
that has nothing to do with the sync itself, and (before this module) reported
it as a token/permissions problem.

Retrying at the application layer rather than ordering the unit after
``network-online.target``: the same race happens on *resume*, where boot
ordering does not apply, and the user services involved cannot depend on a
system target anyway.

Any :class:`RemoteSyncError` is retried, deliberately including
:class:`RepoNotFoundError`. Catching the common parent rather than
:class:`GitHubSyncError` matters since the Firebase cutover:
:class:`FirebaseSyncError` is a *sibling* of :class:`GitHubSyncError`, not a
subclass, so catching the latter let every Firebase failure escape uncaught and
take the whole locker down (``status=1/FAILURE``) instead of degrading to "no
synced workout". Classifying "transient" vs "permanent" would mean
depending on which exception ``crdt_sync`` chains where, which is internal to
that library and has changed before; a few wasted seconds on a genuinely
misconfigured token is a much cheaper mistake than skipping a real retry.
"""

from __future__ import annotations

import logging
from time import sleep
from typing import TYPE_CHECKING

from crdt_sync import RemoteSyncError

from screen_locker._constants import (
    SYNC_RETRY_ATTEMPTS,
    SYNC_RETRY_DELAY_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


def with_sync_retry[T](
    operation: Callable[[], T],
    *,
    description: str,
    attempts: int = SYNC_RETRY_ATTEMPTS,
    delay_seconds: float = SYNC_RETRY_DELAY_SECONDS,
) -> T:
    """Run *operation*, retrying a failed sync with exponential backoff.

    Args:
        operation: The zero-argument sync call to run.
        description: Human phrase naming the operation, used in the retry
            logs (e.g. ``"push PC workouts"``).
        attempts: Total tries, including the first. Values below 1 still run
            the operation exactly once.
        delay_seconds: Base backoff; attempt *n* waits ``delay * 2**(n-1)``.

    Returns:
        Whatever *operation* returns.

    Raises:
        RemoteSyncError: If every attempt failed. The caller keeps its own
            handling — this only buys time, it never hides the outcome.
    """
    last_attempt = max(attempts, 1)
    # Every attempt but the last swallows-and-waits; the last one is run
    # outside the loop so its failure propagates with no unreachable branch.
    for attempt in range(1, last_attempt):
        try:
            return operation()
        except RemoteSyncError as exc:
            wait = delay_seconds * (2 ** (attempt - 1))
            _logger.warning(
                "Could not %s (attempt %d/%d): %s — retrying in %.0fs; "
                "this is normal right after boot or resume, when the "
                "network is not up yet",
                description,
                attempt,
                last_attempt,
                exc,
                wait,
            )
            sleep(wait)

    try:
        return operation()
    except RemoteSyncError as exc:
        _logger.warning(
            "Could not %s after %d attempt(s): %s — giving up",
            description,
            last_attempt,
            exc,
        )
        raise
