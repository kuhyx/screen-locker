"""``python3 -m screen_locker.runnerup_retire``: uninstall RunnerUp, a week on.

What ``runnerup-retire.service`` runs. ``--status`` prints anchor, due date,
marker validity and (with ``--query-phone``) whether RunnerUp is installed;
it never writes and never talks to the phone unless asked. ``--dry-run`` runs
every check, including the read-only adb queries, but writes nothing, pulls
nothing and uninstalls nothing. The exit code is non-zero only for outcomes
that need a human (bad marker, adb missing, failed backup or uninstall).
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import logging
import sys
from typing import TYPE_CHECKING

from screen_locker._runnerup_retire import (
    GRACE,
    Paths,
    derive_anchor,
    run_retire,
)
from screen_locker._runnerup_retire_adb import PHONE_SERIAL, AdbError, Phone
from screen_locker._runnerup_retire_state import load_state
from screen_locker._runnerup_retire_tcx import check_marker

if TYPE_CHECKING:
    from screen_locker._runnerup_retire_adb import PhoneLike

__all__ = ["main", "status_lines"]

_logger = logging.getLogger(__name__)


def _installed_line(phone: PhoneLike, *, query: bool) -> str:
    if not query:
        return "installed: not queried (add --query-phone)"
    try:
        device = phone.find_device()
        if device.serial is None:
            return f"installed: unknown ({device.reason})"
        return f"installed: {'yes' if phone.installed(device.serial) else 'no'}"
    except AdbError as exc:
        _logger.warning("--status could not ask the phone: %s", exc)
        return f"installed: unknown ({exc})"


def status_lines(
    paths: Paths, phone: PhoneLike, now: datetime, *, query_phone: bool = False
) -> list[str]:
    """The ``--status`` report. Read-only: nothing is created or saved."""
    state = load_state(paths.state_file)
    anchor = derive_anchor(paths, state)
    if anchor is None:
        anchor_line, due_line = "anchor: none (no app run credited yet)", "due: never"
    else:
        origin = "stored" if state.anchor_at else "derived, not yet stored"
        due = anchor + GRACE
        days = (due - now).total_seconds() / 86400
        anchor_line = f"anchor: {anchor.isoformat()} ({origin})"
        due_line = f"due: {due:%Y-%m-%d %H:%M} ({days:+.1f} days)"
    marker = check_marker(paths.marker, paths.processed)
    return [
        anchor_line,
        due_line,
        f"marker: {'valid' if marker.ok else 'INVALID'} ({marker.reason})",
        f"done: {state.done_at or 'no'}",
        _installed_line(phone, query=query_phone),
    ]


def main(argv: list[str] | None = None) -> int:
    """CLI entry; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument(
        "--status", action="store_true", help="print state, change nothing"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="check everything, change nothing"
    )
    parser.add_argument(
        "--query-phone", action="store_true", help="with --status: ask adb"
    )
    parser.add_argument("--serial", default=PHONE_SERIAL, help="phone adb serial")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    paths, phone = Paths.default(), Phone(args.serial)
    if args.status:
        now = datetime.now(UTC)
        lines = status_lines(paths, phone, now, query_phone=args.query_phone)
        sys.stdout.write("\n".join(lines) + "\n")
        return 0
    return 0 if run_retire(paths, phone, dry_run=args.dry_run).ok else 1


if __name__ == "__main__":
    sys.exit(main())
