"""Read the morning-session carrot the wake-alarm service signed for today.

The phone's morning (weigh-in, shower, dress, desk) is published to the PC
and distilled by wake-alarm into ``MORNING_SESSION_FILE``. This module never
re-derives the policy: the file carries a signed ``exempt_until``, and the
only decision here is *HMAC ok, dated today, now < exempt_until*. Anything
else -- missing file, stale date, failed session, bad signature -- is "no
skip", i.e. today's ordinary ladder.

The one wrinkle is a PC booted mid-morning: the file is missing or yesterday's
until wake-alarm's ``Persistent=true`` timer catches up, which needs the
network. The enforce path waits for that, bounded; status paths never do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import time
from typing import TYPE_CHECKING

from gatelock.log_integrity import verify_entry_hmac

from screen_locker._constants import MORNING_SESSION_FILE
from screen_locker._day import today_str

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

# Only inside this local window is a non-today file worth waiting for: the
# refresher runs 07:00-11:00, so outside it "not today's" is simply the truth.
MORNING_WINDOW: tuple[tuple[int, int], tuple[int, int]] = ((7, 0), (11, 0))
MORNING_RETRY_SECONDS: float = 30.0
MORNING_POLL_SECONDS: float = 5.0


@dataclass(frozen=True)
class MorningSkip:
    """A skip the morning session earned: what the phone said, and until when."""

    outcome: str
    exempt_until: datetime

    def __str__(self) -> str:
        return f"{self.outcome} session, no lock until {self.exempt_until:%H:%M}"


def _read_verified() -> dict[str, object] | None:
    """The file's entry when it exists, parses and verifies; else None.

    Missing is debug (it is the normal state outside the morning); anything
    else is a warning, because it means the refresher or the key is broken.
    """
    if not MORNING_SESSION_FILE.exists():
        _logger.debug("No morning session file at %s", MORNING_SESSION_FILE)
        return None
    try:
        entry = json.loads(MORNING_SESSION_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Cannot read %s: %s", MORNING_SESSION_FILE, exc)
        return None
    if not isinstance(entry, dict) or not verify_entry_hmac(entry):
        _logger.warning("Morning session file is not a signed object")
        return None
    return entry


def _load_today(now: datetime) -> dict[str, object] | None:
    """Today's verified entry, or None."""
    entry = _read_verified()
    if entry is None or entry.get("date") != today_str(now):
        return None
    return entry


def _skip_from(entry: dict[str, object], now: datetime) -> MorningSkip | None:
    """The skip an entry grants at ``now``, if its window is still open."""
    until = entry.get("exempt_until")
    if not isinstance(until, str):
        return None
    try:
        exempt_until = datetime.fromisoformat(until)
    except ValueError:
        _logger.warning("Morning session exempt_until unreadable: %r", until)
        return None
    if now >= exempt_until:
        return None
    return MorningSkip(outcome=str(entry.get("outcome")), exempt_until=exempt_until)


def _in_window(now: datetime) -> bool:
    (start_h, start_m), (end_h, end_m) = MORNING_WINDOW
    minutes = now.hour * 60 + now.minute
    return start_h * 60 + start_m <= minutes < end_h * 60 + end_m


def morning_skip_today(
    now: datetime | None = None,
    *,
    wait: bool,
    sleep: Callable[[float], None] = time.sleep,
) -> MorningSkip | None:
    """The skip the morning session earned, or None.

    With ``wait`` (the enforce path only), a file that is not today's during
    the morning window is retried for up to ``MORNING_RETRY_SECONDS`` so a
    freshly booted PC gives wake-alarm's catch-up run a chance to land.
    """
    now = (now or datetime.now(tz=UTC)).astimezone()
    entry = _load_today(now)
    waited = 0.0
    while entry is None and wait and _in_window(now) and waited < MORNING_RETRY_SECONDS:
        sleep(MORNING_POLL_SECONDS)
        waited += MORNING_POLL_SECONDS
        now = datetime.now(tz=UTC).astimezone()
        entry = _load_today(now)
    if entry is None:
        if waited:
            _logger.warning(
                "No morning session for today after %.0fs; "
                "is wake-alarm-session.timer running?",
                waited,
            )
        return None
    return _skip_from(entry, now)


def has_workout_skip_today() -> bool:
    """Whether the morning session earned a skip right now. Never waits."""
    return morning_skip_today(wait=False) is not None
