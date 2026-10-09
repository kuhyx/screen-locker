"""``--declare-rest-day``: plan a rest day from the command line.

    python -m screen_locker.screen_lock --declare-rest-day 2026-10-12
    python -m screen_locker.screen_lock --declare-rest-day tomorrow
    python -m screen_locker.screen_lock --declare-rest-day --list

The clock is checked against NTP first and an unconfirmable clock is a
refusal, not a pass: unlike the lock's own check (which fails open when NTP
is unreachable), a wound-back clock with the network off is exactly how
"today" would be passed off as tomorrow.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import logging
import sys
from typing import TYPE_CHECKING

from screen_locker._constants import MAX_CLOCK_SKEW_SECONDS
from screen_locker._day import today_str
from screen_locker._rest_day import declare, rest_days
from screen_locker._time_check import _query_ntp_offset

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)


def _say(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _parse_day(raw: str) -> date:
    today = date.fromisoformat(today_str())
    if raw == "tomorrow":
        return today + timedelta(days=1)
    return date.fromisoformat(raw)


def _clock_confirmed() -> str | None:
    """``None`` if NTP confirms the clock, else why the declaration is refused."""
    offset = _query_ntp_offset()
    if offset is None:
        return "NTP is unreachable, so the clock cannot be confirmed; try online"
    if abs(offset) > MAX_CLOCK_SKEW_SECONDS:
        return f"the clock is off by {abs(offset):.0f}s from NTP"
    return None


def run_declare_rest_day(argv: Sequence[str]) -> int:
    """Declare (or list) rest days. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="screen-locker --declare-rest-day",
        description="Declare a FUTURE rest day (max 2 per ISO week).",
    )
    parser.add_argument("day", nargs="?", help="YYYY-MM-DD or 'tomorrow'")
    parser.add_argument("--list", action="store_true", help="list rest days")
    args = parser.parse_args(list(argv))
    if args.list or args.day is None:
        days = sorted(rest_days())
        _say("\n".join(d.isoformat() for d in days) or "no rest days declared")
        return 0
    try:
        day = _parse_day(args.day)
    except ValueError as exc:
        _logger.warning("Unparsable rest day %r: %s", args.day, exc)
        _say(f"error: {exc}")
        return 2
    refusal = _clock_confirmed()
    if refusal is not None:
        _logger.warning("Rest day refused: %s", refusal)
        _say(f"refused: {refusal}")
        return 1
    result = declare(day)
    if not result.ok:
        _logger.warning("Rest day refused: %s", result.reason)
    _say(result.reason if result.ok else f"refused: {result.reason}")
    return 0 if result.ok else 1
