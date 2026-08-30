"""Waiting for the screen in gatelock's queue, observably.

Separate from ``_queue_state`` on purpose: that module is a pure state-file
reader/writer, which ``_decision_log`` imports to annotate its sync lines.
Putting this function there would close the cycle
``_queue_state -> _decision_log -> _queue_state``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatelock import wait_for_turn

from screen_locker._decision_log import record_run_aborted
from screen_locker._queue_state import publish_queue_wait

if TYPE_CHECKING:
    from gatelock import Arbiter


def wait_for_screen(arbiter: Arbiter) -> None:
    """Wait for the screen, publishing the wait and recording how long it took.

    gatelock's deadline is left at its 6h default on purpose. A higher-ranked
    holder means the screen IS locked, just by someone else -- on 2026-08-30
    the 2h58m wait behind ``wake_alarm`` was a real wake-alarm lock held with
    the grab and VT, not an unenforced machine. Arming over it early would
    draw the workout lock on top of a live alarm, which is the behaviour
    gatelock's queue exists to prevent.

    Args:
        arbiter: Our own published arbiter.
    """
    queued = wait_for_turn(arbiter, on_state=publish_queue_wait)
    if not queued.queued:
        return
    # The decision to lock was recorded when the run started, possibly hours
    # earlier; without this the trail shows "enforced" and then silence until
    # the window finally appears.
    record_run_aborted(
        "queued_behind_holder",
        f"Waited {queued.waited_seconds:.0f}s behind "
        f"{', '.join(queued.blocked_by)} before the screen was free; arming "
        f"now{' (deadline hit)' if queued.timed_out else ''}.",
    )
