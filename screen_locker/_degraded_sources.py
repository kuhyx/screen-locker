"""Which workout backends could not be read on this run, and why.

Split out of :mod:`screen_locker._sync_client` to keep every file under the
250-line cap. Re-exported from there, so existing importers and their patch
targets are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DegradedSource:
    """A workout backend that could not be read on this run.

    ``reason`` is the backend's own error text, kept verbatim so the status
    view and the lock decision can quote something actionable rather than a
    generic "sync problem".
    """

    name: str
    reason: str


# Process-scoped rather than persisted: it describes THIS run's ability to
# read, and a stale marker from an earlier run would be worse than none. The
# lock chain and the pull both happen in one process, so this survives exactly
# as long as it is true.
_degraded: list[DegradedSource] = []


def degraded_sources() -> list[DegradedSource]:
    """Return the backends that failed to answer during this run."""
    return list(_degraded)


def clear_degraded_sources() -> None:
    """Forget recorded failures (called at the start of a fresh check)."""
    _degraded.clear()


def _record_degraded(name: str, reason: str) -> None:
    """Note that *name* could not be read, so callers can stop guessing.

    Logging alone was not enough: on 2026-08-24 the warning was emitted, the
    Firebase read was skipped, and the lock decision still reported
    "0 workouts this week" as though the source had answered "none".
    """
    _degraded.append(DegradedSource(name, reason))
