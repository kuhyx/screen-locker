#!/usr/bin/env python3
"""Add a date to ``scheduled_skips.json`` — the locker's first early exit.

A scheduled skip is the supported way to exempt a specific day without
weakening enforcement for any other day: the lock chain checks it first, and
(since the 2026-08 logging work) records the exemption as a decision, so an
unexpected quiet day is traceable to the date that caused it instead of looking
like the enforcer silently died again.

Kept out of ``arm.sh`` because the file it edits is the one the lock chain
reads: a malformed write is read as "not a skip" and the machine locks anyway,
so this belongs somewhere the repo's linters and tests actually apply.

Usage:
    python3 scripts/add_scheduled_skip.py --date today
    python3 scripts/add_scheduled_skip.py --date 2026-08-20
    python3 scripts/add_scheduled_skip.py --list
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

SKIPS_FILE = (
    Path(__file__).resolve().parent.parent / "screen_locker" / ("scheduled_skips.json")
)


def _today() -> str:
    """Return today's local date as YYYY-MM-DD.

    Local, not UTC: the skip must match the day the user is living in, and the
    lock chain's own ``_today_str`` is local for the same reason.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _report(message: str) -> None:
    """Write one line to stdout (matches the other scripts in this directory)."""
    sys.stdout.write(f"{message}\n")


def load_skips(path: Path) -> list[str]:
    """Return the recorded skip dates, or [] when the file is absent."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # Refuse rather than silently starting a fresh list: overwriting an
        # unreadable file would drop skips the user still expects to hold.
        msg = f"could not read {path}: {exc}"
        msg = f"ERROR: {msg}"
        raise SystemExit(msg) from exc
    if not isinstance(data, list):
        msg = f"ERROR: {path} does not contain a JSON list"
        raise SystemExit(msg)
    return [str(entry) for entry in data]


def add_skip(path: Path, date: str) -> bool:
    """Add ``date`` to the skips file. True if it was newly added."""
    skips = load_skips(path)
    if date in skips:
        return False
    skips.append(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(skips), indent=2) + "\n", encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    """Add the requested date, or list what is already recorded."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        help="date to skip: 'today' or YYYY-MM-DD",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the recorded skip dates and exit",
    )
    args = parser.parse_args(argv)

    if args.list:
        for entry in sorted(load_skips(SKIPS_FILE)):
            _report(entry)
        return 0

    if not args.date:
        parser.error("--date is required (or use --list)")

    date = _today() if args.date == "today" else args.date
    try:
        datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        msg = f"ERROR: {date!r} is not a YYYY-MM-DD date"
        raise SystemExit(msg) from None

    if add_skip(SKIPS_FILE, date):
        _report(f"Added scheduled skip for {date} — the locker will not lock that day.")
    else:
        _report(f"{date} is already a scheduled skip; nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
