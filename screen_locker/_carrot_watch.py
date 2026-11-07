"""An armed lock stands down when wake-alarm's signed carrot lands late.

2026-11-07: the lock armed at 07:49:17 because today's signed
``morning_session.json`` had not landed yet (the refresher lost a network
race). It landed at 07:50:00 (``in_progress``, exempt until 09:13) and nothing
ever re-read it, so the morning session ran under a fullscreen lock. The
startup ladder reads the file once; this is the same verdict, re-asked every
``POLL_MS`` while the window is up.

The decision stays wake-alarm's (signature ok, dated today, now < exempt_until);
this module only decides *when to ask* -- 05:00-11:00 local, the hours the
refresher runs -- and never waits, since it sits on the Tk loop. The file is
read through the ``_morning_session`` module attribute so the test suite's
redirected path applies.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING

from screen_locker import _morning_session

if TYPE_CHECKING:
    from collections.abc import Callable
    from tkinter import Misc

__all__ = ["POLL_MS", "watch_for_carrot"]

_logger = logging.getLogger(__name__)

POLL_MS = 15_000
# Local minutes after midnight; mirrors gatelock.morning_session.MORNING_WINDOW.
_WINDOW_START_MIN = 5 * 60
_WINDOW_END_MIN = 11 * 60


def _local_now() -> datetime:
    return datetime.now(tz=UTC).astimezone()


def _in_window(now: datetime) -> bool:
    return _WINDOW_START_MIN <= now.hour * 60 + now.minute < _WINDOW_END_MIN


def watch_for_carrot(
    root: Misc, on_carrot: Callable[[_morning_session.MorningSkip], None]
) -> None:
    """Hand a late-landing signed carrot to ``on_carrot`` within one poll.

    ``on_carrot`` is the locker's own stand-down (bank the early-bird marker,
    record the decision, then the normal ``close``). Polls on the Tk loop (no
    thread) and stops re-arming once it fires. A failed read is logged and the
    poll goes on: one bad read must not end the only thing watching.
    """

    def _tick() -> None:
        now = _local_now()
        if _in_window(now):
            try:
                skip = _morning_session.morning_skip_today(now, wait=False)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                _logger.warning(
                    "Could not read the morning session while the lock is up "
                    "(%s) — keeping the lock and trying again in %d s",
                    exc,
                    POLL_MS // 1000,
                )
                skip = None
            if skip is not None:
                on_carrot(skip)
                return
        root.after(POLL_MS, _tick)

    root.after(POLL_MS, _tick)
