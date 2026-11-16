"""An open lock window closes itself the moment today's workout is credited.

2026-11-16: the window opened at 07:55:17. kuhy logged a manual workout on the
phone; at 07:59:04 the separate ``_session_stream`` daemon credited it (log row
written, shutdown moved). The open window never noticed: TRY AGAIN only asked
StrongLifts/ADB/HTTP, so it kept saying "stale" and kuhy marked a sick day to
get out. The startup ladder reads ``log.json`` once; this is the same verdict
(``has_logged_today``, HMAC-checked) re-asked whenever the file changes.

Event-driven on the Tk loop, no thread, no new dependency: each poll is one
``stat`` of the log; the file is parsed only when its (mtime, size, inode)
moved. The credit itself was already written by whoever logged it, so closing
here writes nothing and applies nothing -- it just takes the window down.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from screen_locker._decision_log import LockDecision, record_decision

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from tkinter import Misc

__all__ = ["POLL_MS", "CreditStandDownMixin", "watch_for_credit"]

_logger = logging.getLogger(__name__)

# Well inside the 10 s an open window may take to notice a credit.
POLL_MS = 3_000
_UNSEEN: tuple[int, ...] = (-1,)
_ABSENT: tuple[int, ...] = ()


def _signature(log_file: Path) -> tuple[int, ...] | None:
    """(mtime_ns, size, inode) of the log: ``()`` when absent, None on error."""
    # exists() first: a log nobody has written yet is normal, not a fault, and
    # a bare ``except FileNotFoundError`` would be a silent swallow.
    if not log_file.exists():
        return _ABSENT
    try:
        stat = log_file.stat()
    except OSError as exc:
        _logger.warning(
            "Could not stat %s while the lock is up (%s) — keeping the lock "
            "and trying again in %d s",
            log_file,
            exc,
            POLL_MS // 1000,
        )
        return None
    return (stat.st_mtime_ns, stat.st_size, stat.st_ino)


def watch_for_credit(
    root: Misc,
    log_file: Path,
    has_logged: Callable[[], bool],
    on_credit: Callable[[], None],
) -> None:
    """Hand a credit that landed while the window is up to ``on_credit``.

    The first poll always checks (a row may land between startup and arming);
    after that ``has_logged`` runs only when the log's signature changed. A
    failed check is logged and the poll goes on: one bad read must not end the
    only thing watching. Stops re-arming once it fires.
    """
    seen = _UNSEEN

    def _tick() -> None:
        nonlocal seen
        sig = _signature(log_file)
        if sig is not None and sig != seen:
            seen = sig
            try:
                if has_logged():
                    on_credit()
                    return
            except (OSError, ValueError, TypeError, KeyError) as exc:
                _logger.warning(
                    "Could not check %s for a credit while the lock is up "
                    "(%s) — keeping the lock and trying again in %d s",
                    log_file,
                    exc,
                    POLL_MS // 1000,
                )
                seen = _UNSEEN
        root.after(POLL_MS, _tick)

    root.after(POLL_MS, _tick)


class CreditStandDownMixin:
    """The locker's side: leave through the normal ``close`` once credited."""

    def _stand_down_for_credit(self) -> None:
        """Take the window down because today's workout is already credited.

        Same exit as a credited workout, a test hold or a late carrot: lock
        window released, instance lock dropped, exit 0. No row, no credit, no
        penalty -- the logger of the workout already did all of that.
        """
        record_decision(
            LockDecision(
                locked=False,
                reason="workout_credited_elsewhere",
                detail="Today's workout was credited while the lock was up.",
            )
        )
        _logger.warning(
            "Today's workout was credited by another process while the lock "
            "was up — taking the lock down without writing a second credit."
        )
        self.close()
