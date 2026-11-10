"""Outcomes of one RunnerUp-retirement pass, and how loudly each is logged."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import logging

__all__ = ["LEVEL", "Outcome", "RetireResult"]


class Outcome(StrEnum):
    """How a run ended; the value is what the journal shows."""

    UNINSTALLED = "uninstalled"
    ALREADY_GONE = "already-gone"
    ALREADY_DONE = "already-done"
    NO_ANCHOR = "no-anchor"
    SOURCES_MISSING = "sources-missing"
    NOT_DUE = "not-due"
    DRY_RUN = "dry-run"
    DEVICE_ABSENT = "device-absent"
    MARKER_INVALID = "marker-invalid"
    ADB_MISSING = "adb-missing"
    PHONE_ERROR = "phone-error"
    BACKUP_FAILED = "backup-failed"
    UNINSTALL_FAILED = "uninstall-failed"


# Level per outcome; the failures also make the unit exit non-zero.
LEVEL = {
    Outcome.DEVICE_ABSENT: logging.WARNING,
    Outcome.SOURCES_MISSING: logging.WARNING,
    Outcome.MARKER_INVALID: logging.WARNING,
    Outcome.ADB_MISSING: logging.ERROR,
    Outcome.PHONE_ERROR: logging.ERROR,
    Outcome.BACKUP_FAILED: logging.ERROR,
    Outcome.UNINSTALL_FAILED: logging.ERROR,
}
_NONZERO = frozenset(
    {
        Outcome.MARKER_INVALID,
        Outcome.ADB_MISSING,
        Outcome.PHONE_ERROR,
        Outcome.BACKUP_FAILED,
        Outcome.UNINSTALL_FAILED,
    }
)


@dataclass(frozen=True)
class RetireResult:
    """What happened and why, in a sentence a human can act on."""

    outcome: Outcome
    reason: str
    logged: bool = False  # the failure was already logged where it was caught

    @property
    def ok(self) -> bool:
        """False for outcomes the unit should surface as failed."""
        return self.outcome not in _NONZERO
