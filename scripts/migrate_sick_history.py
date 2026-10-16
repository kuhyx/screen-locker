#!/usr/bin/env python3
"""Move ``sick_history.json``'s sick days into the shared ``sickdays`` pool, once.

screen-locker's old sick day lived in its own file, next to a budget, a
justification log, commitments and a debt counter -- all gone now. A sick day
is a date in the fleet-wide ``sickdays`` pool, nothing else, so only the
dates move (2026-06-21 and 2026-07-24 on kuhy's PC). Both are in the past,
which only ``sickdays.import_legacy`` may write.

Idempotent, so ``install.sh`` runs it on every install:

- no history file: nothing to do, exit 0;
- every date already sick in the pool: nothing is rewritten (no new HLC tick,
  no audit line), the file is removed;
- otherwise the missing dates are imported, read back from the pool, and only
  when every one is there is the file removed. Any failure leaves it in
  place and exits 1, so the next run tries again.

    scripts/migrate_sick_history.py --dry-run   # show what would happen
    scripts/migrate_sick_history.py             # do it

``--history-file`` and ``--pool-dir`` point it at copies (for tests and
rehearsals); without ``--pool-dir`` the real pool is written.

Output goes through ``_report`` rather than ``print``: ruff's T201 fix is
unsafe and deletes the whole call.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import logging
from pathlib import Path
import sys

import sickdays

DEFAULT_HISTORY_FILE = (
    Path(__file__).resolve().parent.parent / "screen_locker" / "sick_history.json"
)

_logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """The history could not be read or the pool did not take every date."""


def _report(message: str) -> None:
    """Write one line to stdout, un-deletable by an autofixer."""
    sys.stdout.write(f"{message}\n")


def read_sick_days(path: Path) -> list[date]:
    """The ``sick_days`` dates in ``path``, ascending.

    Raises:
        MigrationError: The file is unreadable or holds something that is not
            a list of ``YYYY-MM-DD`` dates.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        msg = f"could not read {path}: {exc}"
        raise MigrationError(msg) from exc
    days = raw.get("sick_days", []) if isinstance(raw, dict) else None
    if not isinstance(days, list):
        msg = f"{path} has no list of sick_days"
        raise MigrationError(msg)
    try:
        return sorted({date.fromisoformat(str(entry)) for entry in days})
    except ValueError as exc:
        msg = f"{path} holds a sick day that is not a YYYY-MM-DD date: {exc}"
        raise MigrationError(msg) from exc


def migrate(
    history: Path, paths: sickdays.Paths | None, *, dry_run: bool
) -> list[date]:
    """Import ``history``'s dates into the pool, verify, remove ``history``.

    Returns:
        The dates newly written (or, on a dry run, that would be).

    Raises:
        MigrationError: Unreadable history, a refusing pool, or a date that
            is not in the pool after the import.
    """
    days = read_sick_days(history)
    log_path = paths.log if paths is not None else None
    missing = [d for d in days if d not in sickdays.sick_days(log_path=log_path)]
    if dry_run:
        return missing
    try:
        written = sickdays.import_legacy(missing, paths=paths)
    except sickdays.SickDayError as exc:
        msg = f"the sickdays pool refused the import: {exc}"
        raise MigrationError(msg) from exc
    absent = sorted(set(days) - sickdays.sick_days(log_path=log_path))
    if absent:
        msg = f"not in the pool after the import: {', '.join(map(str, absent))}"
        raise MigrationError(msg)
    history.unlink()
    return written


def main(argv: list[str] | None = None) -> int:
    """Run the migration. Returns 0 when done or nothing to do, 1 on failure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history-file", type=Path, default=DEFAULT_HISTORY_FILE)
    parser.add_argument("--pool-dir", type=Path, help="pool directory (default: real)")
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would change, write nothing"
    )
    args = parser.parse_args(argv)
    history: Path = args.history_file
    if not history.exists():
        _report(f"no {history} -- nothing to migrate")
        return 0
    paths = sickdays.Paths.under(args.pool_dir) if args.pool_dir else None
    try:
        days = migrate(history, paths, dry_run=args.dry_run)
    except MigrationError as exc:
        _logger.warning(
            "sick-history migration failed, %s left in place: %s", history, exc
        )
        _report(f"FAILED: {exc} ({history} left in place)")
        return 1
    listed = ", ".join(map(str, days)) or "none"
    if args.dry_run:
        _report(f"would import: {listed}; {history} would be removed")
    else:
        _report(f"imported: {listed}; every sick day is in the pool; {history} removed")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
