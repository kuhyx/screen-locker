"""Early bird window detection and pending-state helpers for ScreenLocker.

The early-bird "still waiting to see if a real workout shows up" flag is a
same-day pending marker, not a workout — it is intentionally kept out of
log.json (which is reserved for real outcomes) and instead lives in
its own self-expiring, HMAC-signed state file, mirroring the pattern used by
``wake_alarm._state`` in the companion wake-alarm service. It is written when
the wake-alarm carrot defers the lock, so that when the carrot ends the next
run tries a phone/RunnerUp workout before locking.
"""

from __future__ import annotations

import json
import logging

from gatelock.log_integrity import compute_entry_hmac

from screen_locker._compliance_state import is_early_bird_pending
from screen_locker._constants import EARLY_BIRD_PENDING_FILE
from screen_locker._day import today_str
from screen_locker._morning_session import MorningSkip, morning_skip_today

_logger = logging.getLogger(__name__)


def _today_str() -> str:
    """Return today's LOCAL date as YYYY-MM-DD (see ``screen_locker._day``)."""
    return today_str()


class EarlyBirdMixin:
    """Mixin providing the early-bird window check and pending-state helpers.

    Since 2026-09-20 the window is not a wall clock but the wake-alarm
    morning-session carrot: open exactly while wake-alarm's signed
    ``morning_session.json`` says the morning is being earned (before the
    alarm, during the session, and until 11:00 once it completed in time).
    The old 05:00-08:30 clock locked someone who got up at 07:00 -- the
    opposite of the goal -- and it was a second mechanism next to the one
    that actually knows whether the user is up.
    """

    _morning_skip: MorningSkip | None = None

    def _is_early_bird_time(self) -> bool:
        """Whether the wake-alarm carrot is in force right now.

        Waits (bounded) for a freshly booted PC's refresher; the verdict is
        kept on the instance so the skip detail can quote its ``exempt_until``.
        """
        self._morning_skip = morning_skip_today(wait=True)
        return self._morning_skip is not None

    def _is_early_bird_pending(self) -> bool:
        """Check if today has an unresolved early-bird pending marker."""
        return is_early_bird_pending(EARLY_BIRD_PENDING_FILE)

    def _save_early_bird_pending(self) -> None:
        """Save today's early-bird pending marker (self-expires tomorrow)."""
        state: dict[str, object] = {"date": _today_str()}
        signature = compute_entry_hmac(state)
        if signature is not None:
            state["hmac"] = signature
        else:
            _logger.warning("HMAC key unavailable — saving unsigned pending marker")
        try:
            with EARLY_BIRD_PENDING_FILE.open("w") as f:
                json.dump(state, f, indent=2)
        except OSError as exc:
            _logger.warning("Could not save early-bird pending marker: %s", exc)
