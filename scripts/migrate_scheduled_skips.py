#!/usr/bin/env python3
"""Move ``scheduled_skips.json`` into the shared free-day pool, once.

screen-locker's scheduled skips were the first version of "a day when the
gate stands down", and the only one any app had. freedays generalises them:
the same idea, but one marked day now stands down every gate app at once.

This copies the dates across and leaves the original file untouched, so the
migration can be inspected -- and rerun -- before anything is deleted.
Rerunning is safe: a date already in the pool is reported and skipped, never
duplicated or double-counted.

    scripts/migrate_scheduled_skips.py --dry-run   # show what would happen
    scripts/migrate_scheduled_skips.py             # do it

Every imported date is in the past, and ``freedays.mark`` deliberately
refuses to backdate -- that refusal is what stops a gate you already failed
being erased afterwards. Passing ``now=day`` supplies the day itself as the
reference instead of reaching for the system clock, which is the one honest
way to say "this day was taken, and it was taken then". Each lands as spent
(``consumed``), which is correct: these days happened.

Output goes through ``_report`` rather than ``print``. ruff's T201 fix is
*unsafe* -- it deletes the whole call, message and all -- and it did exactly
that to the first draft of this file, leaving a migration that moved data
while appearing to do nothing.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import logging
from pathlib import Path
import sys

import freedays

DEFAULT_SKIPS_FILE = (
    Path(__file__).resolve().parent.parent / "screen_locker" / "scheduled_skips.json"
)
_REASON = "migrated from screen-locker scheduled_skips.json"

_logger = logging.getLogger(__name__)


def _report(message: str) -> None:
    """Write one line to stdout, un-deletable by an autofixer."""
    sys.stdout.write(f"{message}\n")


def read_skips(path: Path) -> list[date]:
    """Return the dates listed in ``path``, ascending.

    Raises:
        SystemExit: If the file is missing or is not a JSON list of dates.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        msg = f"no scheduled-skips file at {path} -- nothing to migrate"
        raise SystemExit(msg) from exc
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"could not read {path}: {exc}"
        raise SystemExit(msg) from exc
    if not isinstance(raw, list):
        sys.exit(f"{path} is not a JSON list of dates")
    try:
        return sorted(date.fromisoformat(str(entry)) for entry in raw)
    except ValueError as exc:
        msg = f"{path} holds something that is not a YYYY-MM-DD date: {exc}"
        raise SystemExit(msg) from exc


def migrate(days: list[date], *, dry_run: bool) -> int:
    """Mark each day in the shared pool. Returns how many were newly added."""
    added = 0
    for day in days:
        iso = freedays.to_iso(day)
        if freedays.is_free_day(day):
            _report(f"  {iso}  already in the pool, leaving it alone")
            continue
        if dry_run:
            _report(f"  {iso}  would be added")
            added += 1
            continue
        try:
            freedays.mark(day, reason=_REASON, now=day)
        except freedays.FreeDayError as exc:
            _logger.warning("the pool refused %s: %s", iso, exc)
            _report(f"  {iso}  REFUSED: {exc}")
            continue
        _report(f"  {iso}  added")
        added += 1
    return added


def _report_budget(days: list[date]) -> None:
    """Print each affected year's remaining budget."""
    years = sorted({day.year for day in days})
    for year in years:
        status = freedays.status(year=year)
        _report(
            f"{year}: {status.spent} of {status.budget} free days spent, "
            f"{status.left} left"
        )


def main(argv: list[str] | None = None) -> int:
    """Read the skips file and copy its dates into the shared pool."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skips-file", type=Path, default=DEFAULT_SKIPS_FILE)
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would change, write nothing"
    )
    args = parser.parse_args(argv)

    days = read_skips(args.skips_file)
    _report(f"{len(days)} scheduled skip(s) in {args.skips_file}:")
    added = migrate(days, dry_run=args.dry_run)
    _report_budget(days)

    verb = "would be added" if args.dry_run else "added"
    _report(f"{added} {verb}.")
    if not args.dry_run and added:
        _report(f"{args.skips_file} left in place -- delete it once this looks right.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
