#!/usr/bin/env python3
"""Mark a day free, for this app and every other gate app at once.

This used to append to ``screen_locker/scheduled_skips.json``, which only
screen-locker read. That file is no longer consulted by anything: the lock
chain now asks the shared pool (``~/utils/freedays``), so a day taken here
also stands down diet-guard, wake-alarm, leetcode-guard and home-guard.

Kept as a thin wrapper rather than deleted because ``arm.sh`` calls it, and
because this is the name already in muscle memory. ``freedays mark`` does
exactly the same thing.

    scripts/add_scheduled_skip.py --date today
    scripts/add_scheduled_skip.py --date 2026-12-24

The date is **local**. The old version computed a local "today" while the
lock chain compared against a UTC one, so a skip added near midnight could
name a date the chain never matched. freedays owns "what is today" for both
sides now, so that disagreement cannot recur.
"""

from __future__ import annotations

import argparse
import logging
import sys

import freedays

_logger = logging.getLogger(__name__)


def _report(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def main(argv: list[str] | None = None) -> int:
    """Mark the requested day free in the shared pool.

    Returns:
        ``0`` when the day is free (including when it already was), ``1``
        when the pool refused, ``2`` when the date could not be parsed.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--date",
        default="today",
        help="YYYY-MM-DD, or 'today'/'tomorrow' (default: today)",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="optional free text; never required",
    )
    args = parser.parse_args(argv)

    try:
        day = freedays.resolve(args.date)
    except ValueError as exc:
        _logger.warning("could not parse the requested date: %s", exc)
        _report(f"error: {exc}")
        return 2

    iso = freedays.to_iso(day)
    if freedays.is_free_day(day):
        _report(f"{iso} is already a free day; nothing to do")
        return 0

    try:
        freedays.mark(day, reason=args.reason)
    except freedays.FreeDayError as exc:
        _logger.warning("the pool refused %s: %s", iso, exc)
        _report(f"error: {exc}")
        return 1

    left = freedays.status(year=day.year).left
    _report(f"{iso} is now a free day for every gate app ({left} left in {day.year})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
