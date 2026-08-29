"""Early bird window detection and pending-state helpers for ScreenLocker.

The early-bird "still waiting to see if a real workout shows up" flag is a
same-day pending marker, not a workout — it is intentionally kept out of
log.json (which is reserved for real outcomes) and instead lives in
its own self-expiring, HMAC-signed state file, mirroring the pattern used by
``_wake_state.py`` for the companion wake_alarm service.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging

from gatelock.log_integrity import compute_entry_hmac

from screen_locker._compliance_state import is_early_bird_pending
from screen_locker._constants import (
    EARLY_BIRD_END_HOUR,
    EARLY_BIRD_END_MINUTE,
    EARLY_BIRD_PENDING_FILE,
    EARLY_BIRD_START_HOUR,
    EXTRA_BENEFITS_FILE,
)
from screen_locker._extra_benefits import has_extended_early_bird

_logger = logging.getLogger(__name__)


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


class EarlyBirdMixin:
    """Mixin providing early-bird time window checks and pending-state helpers."""

    def _get_local_time_minutes(self) -> int:
        """Return current local time as minutes from midnight."""
        now = datetime.now(tz=UTC).astimezone()
        return now.hour * 60 + now.minute

    def _is_early_bird_time(self) -> bool:
        """Return True if current local time is in the early bird window.

        Normally the window closes at 08:30. When the current ISO week has an
        extended early-bird reward (earned by 5+ workouts the prior week) the
        window extends to 09:00.
        """
        minutes = self._get_local_time_minutes()
        start = EARLY_BIRD_START_HOUR * 60
        if has_extended_early_bird(EXTRA_BENEFITS_FILE):
            end = 9 * 60  # 09:00
        else:
            end = EARLY_BIRD_END_HOUR * 60 + EARLY_BIRD_END_MINUTE
        return start <= minutes < end

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
