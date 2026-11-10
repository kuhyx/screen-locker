"""RunnerUp retirement: when it fires, what it refuses, and what it records."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

import pytest

from screen_locker import _runnerup_retire as rr
from screen_locker._runnerup_retire import Outcome, Paths, run_retire
from screen_locker._runnerup_retire_adb import AdbError, Device
from screen_locker._runnerup_retire_state import RetireState, load_state, save_state
from screen_locker.tests._retire_helpers import (
    ANCHOR,
    DUE,
    RUN,
    FakePhone,
    put_marker,
    world,
)

if TYPE_CHECKING:
    from pathlib import Path


def go(paths: Paths, phone: FakePhone, now: datetime = DUE, *, dry_run: bool = False):
    """Go."""
    return run_retire(paths, phone, now, dry_run=dry_run)


def test_no_anchor_never_touches_anything(tmp_path: Path) -> None:
    """Test no anchor never touches anything."""
    paths = world(tmp_path, anchored=False)
    phone = FakePhone()
    result = go(paths, phone, DUE + timedelta(days=900))
    assert result.outcome is Outcome.NO_ANCHOR
    assert result.ok
    assert not phone.calls
    assert not paths.state_file.exists()


def test_missing_sources_are_a_warning_not_a_quiet_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test missing sources are a warning not a quiet nothing."""
    paths = Paths(tmp_path / "s.json", tmp_path / "nodrop", tmp_path / "nolog.json")
    with caplog.at_level(logging.INFO):
        result = go(paths, FakePhone())
    assert result.outcome is Outcome.SOURCES_MISSING
    assert result.ok
    assert "nodrop" in result.reason
    assert "nolog.json" in result.reason
    assert caplog.records[-1].levelno == logging.WARNING


def test_no_anchor_says_how_many_app_runs_it_saw(tmp_path: Path) -> None:
    """Test no anchor says how many app runs it saw."""
    paths = world(tmp_path, anchored=False)
    assert "(1 app TCX on disk)" in go(paths, FakePhone()).reason


def test_not_due_persists_the_anchor_and_says_when(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test not due persists the anchor and says when."""
    paths = world(tmp_path)
    with caplog.at_level(logging.INFO):
        result = go(paths, FakePhone(), DUE - timedelta(minutes=1))
    assert result.outcome is Outcome.NOT_DUE
    assert "2026-11-08 10:45" in result.reason
    assert load_state(paths.state_file).anchor == ANCHOR
    assert [r.levelno for r in caplog.records] == [logging.INFO]


def test_stored_anchor_wins_over_the_log(tmp_path: Path) -> None:
    """Test stored anchor wins over the log."""
    paths = world(tmp_path, anchored=False)
    save_state(paths.state_file, RetireState(anchor_at=ANCHOR.isoformat()))
    assert go(paths, FakePhone(), ANCHOR).outcome is Outcome.NOT_DUE


def test_dry_run_writes_nothing_and_stops_before_the_phone_changes(
    tmp_path: Path,
) -> None:
    """Test dry run writes nothing and stops before the phone changes."""
    paths = world(tmp_path)
    phone = FakePhone()
    result = go(paths, phone, dry_run=True)
    assert result.outcome is Outcome.DRY_RUN
    assert phone.calls == ["installed S"]
    assert not paths.state_file.exists()
    gone = go(paths, FakePhone(present=False), dry_run=True)
    assert gone.outcome is Outcome.ALREADY_GONE
    assert not paths.state_file.exists()


@pytest.mark.parametrize("variant", ["missing", "mismatch"])
def test_invalid_marker_blocks_the_uninstall_loudly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, variant: str
) -> None:
    """Test invalid marker blocks the uninstall loudly."""
    paths = world(tmp_path, marker=variant == "mismatch")
    if variant == "mismatch":
        put_marker(paths.watch_dir, [RUN], count=2)
    phone = FakePhone()
    with caplog.at_level(logging.WARNING):
        result = go(paths, phone)
    assert result.outcome is Outcome.MARKER_INVALID
    assert not result.ok
    assert "NOT uninstalling" in result.reason
    assert not phone.calls
    assert caplog.records[-1].levelno == logging.WARNING


def test_adb_missing_is_a_failure(tmp_path: Path) -> None:
    """Test adb missing is a failure."""
    result = go(world(tmp_path), FakePhone(adb=False))
    assert result.outcome is Outcome.ADB_MISSING
    assert not result.ok


def test_absent_phone_retries_quietly_but_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test absent phone retries quietly but warns."""
    phone = FakePhone(device=Device(None, "phone S is not attached"))
    with caplog.at_level(logging.WARNING):
        result = go(world(tmp_path), phone)
    assert result.outcome is Outcome.DEVICE_ABSENT
    assert result.ok
    assert "not attached" in caplog.text
    assert not phone.calls


def test_adb_error_while_asking_is_a_logged_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test adb error while asking is a logged failure."""
    phone = FakePhone(ask_error=AdbError("server died"))
    with caplog.at_level(logging.ERROR):
        result = go(world(tmp_path), phone)
    assert result.outcome is Outcome.PHONE_ERROR
    assert not result.ok
    assert len(caplog.records) == 1  # logged once, where it was caught


def test_already_uninstalled_is_recorded_done(tmp_path: Path) -> None:
    """Test already uninstalled is recorded done."""
    paths = world(tmp_path)
    result = go(paths, FakePhone(present=False))
    assert result.outcome is Outcome.ALREADY_GONE
    assert load_state(paths.state_file).done_at
    assert go(paths, FakePhone()).outcome is Outcome.ALREADY_DONE


def test_full_run_backs_up_then_uninstalls_then_never_again(tmp_path: Path) -> None:
    """Test full run backs up then uninstalls then never again."""
    paths = world(tmp_path)
    phone = FakePhone()
    result = go(paths, phone)
    assert result.outcome is Outcome.UNINSTALLED
    assert phone.calls == ["installed S", "backup", "uninstall"]
    backup = paths.watch_dir / "runnerup_phone_backup_2026-11-08"
    assert backup.is_dir()
    assert not list(paths.watch_dir.glob("*.tcx"))  # nothing top-level
    state = load_state(paths.state_file)
    assert state.anchor == ANCHOR
    assert state.backup_path == str(backup)
    assert state.done_at
    again = FakePhone()
    assert go(paths, again).outcome is Outcome.ALREADY_DONE
    assert not again.calls


@pytest.mark.parametrize("error", [AdbError("short pull"), OSError("disk full")])
def test_failed_backup_blocks_the_uninstall(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    """Test failed backup blocks the uninstall."""
    phone = FakePhone(backup_error=error)
    with caplog.at_level(logging.ERROR):
        result = go(world(tmp_path), phone)
    assert result.outcome is Outcome.BACKUP_FAILED
    assert not result.ok
    assert "uninstall" not in phone.calls
    assert str(error) in caplog.text


def test_failed_uninstall_keeps_the_backup_for_the_retry(tmp_path: Path) -> None:
    """Test failed uninstall keeps the backup for the retry."""
    paths = world(tmp_path)
    first = FakePhone(uninstall_error=AdbError("DELETE_FAILED_DEVICE_POLICY_MANAGER"))
    result = go(paths, first)
    assert result.outcome is Outcome.UNINSTALL_FAILED
    assert not result.ok
    assert not load_state(paths.state_file).done_at
    retry = FakePhone()
    assert go(paths, retry, DUE + timedelta(days=1)).outcome is Outcome.UNINSTALLED
    assert retry.calls == ["installed S", "uninstall"]  # no second backup


def test_default_paths_are_the_module_constants() -> None:
    """Test default paths are the module constants."""
    paths = Paths.default()
    assert paths.state_file == rr.STATE_FILE
    assert paths.marker == rr.WATCH_DIR / rr.MARKER_NAME
    assert paths.processed == rr.WATCH_DIR / "processed"
    assert paths.anchor_dirs() == (rr.WATCH_DIR, rr.WATCH_DIR / "processed")


def test_run_retire_defaults_to_the_real_clock(tmp_path: Path) -> None:
    """Test run retire defaults to the real clock."""
    paths = world(tmp_path)
    assert run_retire(paths, FakePhone(), dry_run=True).outcome is Outcome.DRY_RUN
