"""Retire the stock RunnerUp app a week after the PC first credits an app run.

kuhy's workout_app records runs itself now. Once the PC has credited one of
them, RunnerUp is redundant: seven days later (``GRACE``) it is backed up and
uninstalled, but only if the app has imported the RunnerUp history (a marker
the app writes) and that import matches what ``processed/`` holds. With no
anchor (no app run ever credited) it never uninstalls.

The phone is not always on USB, so ``runnerup-retire.timer`` retries daily
until this succeeds. Every outcome is a typed :class:`RetireResult` whose
reason is logged at the level it deserves: ``info`` for the normal "not due
yet", ``warning`` for a skip that needs attention, ``error`` for a failure.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from screen_locker._runnerup_retire_adb import PACKAGE, AdbError
from screen_locker._runnerup_retire_state import load_state, save_state
from screen_locker._runnerup_retire_tcx import check_marker, find_anchor

if TYPE_CHECKING:
    from screen_locker._runnerup_retire_adb import Phone
    from screen_locker._runnerup_retire_state import RetireState

_logger = logging.getLogger(__name__)

GRACE = timedelta(days=7)
STATE_FILE = Path.home() / ".local" / "state" / "screen-locker" / "runnerup_retire.json"
WATCH_DIR = Path.home() / "data" / "cloud" / "RunnerUp"
LOG_FILE = Path(__file__).resolve().parent / "log.json"
MARKER_NAME = ".workout_app_import.json"


class Outcome(StrEnum):
    """How a run ended; the value is what the journal shows."""

    UNINSTALLED = "uninstalled"
    ALREADY_GONE = "already-gone"
    ALREADY_DONE = "already-done"
    NO_ANCHOR = "no-anchor"
    NOT_DUE = "not-due"
    DRY_RUN = "dry-run"
    DEVICE_ABSENT = "device-absent"
    MARKER_INVALID = "marker-invalid"
    ADB_MISSING = "adb-missing"
    PHONE_ERROR = "phone-error"
    BACKUP_FAILED = "backup-failed"
    UNINSTALL_FAILED = "uninstall-failed"


# Level per outcome; the failures also make the unit exit non-zero.
_LEVEL = {
    Outcome.DEVICE_ABSENT: logging.WARNING,
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


@dataclass(frozen=True)
class Paths:
    """Every on-disk location, so tests (and ``--status``) can redirect them."""

    state_file: Path
    watch_dir: Path
    log_file: Path

    @classmethod
    def default(cls) -> Paths:
        """The live locations (read at call time so tests can patch them)."""
        return cls(STATE_FILE, WATCH_DIR, LOG_FILE)

    @property
    def processed(self) -> Path:
        """Where endurain-import files the RunnerUp exports it has handled."""
        return self.watch_dir / "processed"

    @property
    def marker(self) -> Path:
        """The app's historic-import marker."""
        return self.watch_dir / MARKER_NAME

    def anchor_dirs(self) -> tuple[Path, Path]:
        """Where an app run's TCX can sit: the drop dir, then ``processed/``."""
        return (self.watch_dir, self.processed)


def derive_anchor(paths: Paths, state: RetireState) -> datetime | None:
    """The stored anchor, else the first credit of an app run found on disk."""
    return state.anchor or find_anchor(paths.log_file, paths.anchor_dirs())


def _finish(paths: Paths, state: RetireState, now: datetime, why: str) -> None:
    save_state(
        paths.state_file, replace(state, done_at=now.isoformat(), done_reason=why)
    )


def _probe(phone: Phone) -> RetireResult | tuple[str, bool]:
    """``(serial, installed)`` if the phone answers, else the result explaining why."""
    if not phone.available():
        return RetireResult(
            Outcome.ADB_MISSING, "adb is not installed (pacman -S android-tools)"
        )
    try:
        device = phone.find_device()
        if device.serial is None:
            return RetireResult(
                Outcome.DEVICE_ABSENT, f"{device.reason}; retrying next run"
            )
        return device.serial, phone.installed(device.serial)
    except AdbError as exc:
        _logger.exception("RunnerUp retirement: asking the phone failed")
        return RetireResult(
            Outcome.PHONE_ERROR, f"asking the phone failed: {exc}", logged=True
        )


def _backup(
    paths: Paths, phone: Phone, state: RetireState, serial: str, now: datetime
) -> RetireState | RetireResult:
    """Back the phone's exports up once; a later retry reuses a finished backup."""
    if state.backup_path and Path(state.backup_path).is_dir():
        return state
    final = paths.watch_dir / f"runnerup_phone_backup_{now:%Y-%m-%d}"
    try:
        made, files = phone.backup(serial, final)
    except (AdbError, OSError) as exc:
        _logger.exception("RunnerUp retirement: backup failed")
        return RetireResult(Outcome.BACKUP_FAILED, f"backup failed: {exc}", logged=True)
    _logger.info("Backed up %d RunnerUp TCX files to %s", files, made)
    state = replace(state, backup_path=str(made))
    save_state(paths.state_file, state)
    return state


def _retire(
    paths: Paths, phone: Phone, state: RetireState, now: datetime, *, dry_run: bool
) -> RetireResult:
    """Everything after "it is due and the marker is good": the phone steps."""
    probed = _probe(phone)
    if isinstance(probed, RetireResult):
        return probed
    serial, present = probed
    if not present:
        if not dry_run:
            _finish(paths, state, now, f"{PACKAGE} was already absent")
        return RetireResult(Outcome.ALREADY_GONE, f"{PACKAGE} is already absent")
    if dry_run:
        return RetireResult(
            Outcome.DRY_RUN, "would back up and uninstall (no changes made)"
        )
    backed = _backup(paths, phone, state, serial, now)
    if isinstance(backed, RetireResult):
        return backed
    try:
        phone.uninstall(serial)
    except AdbError as exc:
        _logger.exception("RunnerUp retirement: uninstall failed")
        return RetireResult(
            Outcome.UNINSTALL_FAILED, f"uninstall failed: {exc}", logged=True
        )
    _finish(paths, backed, now, f"uninstalled after backup to {backed.backup_path}")
    return RetireResult(
        Outcome.UNINSTALLED,
        f"{PACKAGE} uninstalled; backup in {backed.backup_path}",
    )


def _gate(
    paths: Paths, state: RetireState, now: datetime, *, dry_run: bool
) -> RetireState | RetireResult:
    """The no-phone checks; a state back means "due, marker good: go on"."""
    if state.done_at:
        return RetireResult(
            Outcome.ALREADY_DONE, f"done {state.done_at}: {state.done_reason}"
        )
    anchor = derive_anchor(paths, state)
    if anchor is None:
        return RetireResult(
            Outcome.NO_ANCHOR, "no app-recorded run credited yet; nothing to retire"
        )
    if not state.anchor_at:
        state = replace(state, anchor_at=anchor.isoformat())
        if not dry_run:
            save_state(paths.state_file, state)
    due = anchor + GRACE
    if now < due:
        return RetireResult(
            Outcome.NOT_DUE, f"due {due:%Y-%m-%d %H:%M} (anchor {anchor:%Y-%m-%d})"
        )
    marker = check_marker(paths.marker, paths.processed)
    if not marker.ok:
        return RetireResult(
            Outcome.MARKER_INVALID, f"{marker.reason}; NOT uninstalling"
        )
    return state


def run_retire(
    paths: Paths, phone: Phone, now: datetime | None = None, *, dry_run: bool = False
) -> RetireResult:
    """One pass: uninstall RunnerUp if (and only if) every condition holds."""
    when = now or datetime.now(UTC)
    gated = _gate(paths, load_state(paths.state_file), when, dry_run=dry_run)
    if isinstance(gated, RetireResult):
        result = gated
    else:
        result = _retire(paths, phone, gated, when, dry_run=dry_run)
    if not result.logged:
        _logger.log(
            _LEVEL.get(result.outcome, logging.INFO),
            "RunnerUp retirement: %s: %s",
            result.outcome.value,
            result.reason,
        )
    return result
