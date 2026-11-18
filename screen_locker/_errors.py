"""Error and slow-wait reporting for screen-locker (utils DOCS-app-errors.md).

``install`` runs once from the CLI entry point: uncaught, thread and Tk
callback errors, and a Tk loop frozen over 1 s, go to the app-errors spool,
from which the PC's ingest files a board ticket. Only the CLI installs it, so
tests that build a lock window never touch the real spool.
"""

from __future__ import annotations

from dataclasses import dataclass

from gatelock import error_report

APP = "screen-locker"
REPO = "kuhyx/screen-locker"


@dataclass
class _Slot:
    """Holds the process's reporter once installed."""

    reporter: error_report.Reporter | None = None


#: The installed reporter (``SLOT.reporter``); None until ``install``.
SLOT = _Slot()


def install() -> error_report.Reporter:
    """Hook this process's errors once; return the reporter."""
    SLOT.reporter = error_report.install(APP, REPO)
    return SLOT.reporter
