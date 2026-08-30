"""Tests for the run-modes that never reach the lock decision.

Split out of test_decision_log.py for the 250-line cap. These cover the two
records that keep "this run did not decide" distinguishable from "this run
decided not to lock" -- the confusion that hid a 13-day enforcement outage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._decision_log import (
    read_decisions,
    record_no_decision,
    record_run_aborted,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_PKG = "screen_locker._decision_log"


class TestRecordNoDecision:
    """Modes that never evaluate the lock must be distinguishable."""

    def test_records_mode_and_null_lock(self, tmp_path: Path) -> None:
        """'did not decide' must not look like 'decided not to lock'."""
        target = tmp_path / "d.jsonl"
        record_no_decision("--sync-only", log_file=target)
        (record,) = read_decisions(log_file=target)
        assert record["locked"] is None
        assert record["reason"] == "mode_makes_no_decision"
        assert record["mode"] == "--sync-only"

    def test_it_reports_what_the_locker_was_doing(self, tmp_path: Path) -> None:
        """The every-15-minutes heartbeat is where this gets observed.

        systemd cannot start a second instance of an already-active
        Type=simple unit, so on 2026-08-30 the 09:30-14:00 timer triggers were
        silent no-ops and these sync lines were the only records in the
        window -- saying nothing about the run that had decided to lock at
        09:01 and was still waiting behind wake_alarm.
        """
        target = tmp_path / "d.jsonl"
        with (
            patch(f"{_PKG}.locker_unit_active", return_value=True),
            patch(
                f"{_PKG}.read_queue_wait",
                return_value={"blocked_by": ["wake_alarm"], "elapsed_seconds": 9000},
            ),
        ):
            record_no_decision("--sync-only", log_file=target)
        (record,) = read_decisions(log_file=target)
        assert record["locker_running"] is True
        assert record["queued_behind"] == ["wake_alarm"]

    def test_an_unqueued_run_omits_the_blocker_field(self, tmp_path: Path) -> None:
        """No blocker is the normal case; it must not add noise to every row."""
        target = tmp_path / "d.jsonl"
        with (
            patch(f"{_PKG}.locker_unit_active", return_value=False),
            patch(f"{_PKG}.read_queue_wait", return_value=None),
        ):
            record_no_decision("--sync-only", log_file=target)
        (record,) = read_decisions(log_file=target)
        assert "queued_behind" not in record
        assert record["locker_running"] is False


class TestRecordRunAborted:
    """A run that meant to decide and could not is its own outcome."""

    def test_it_records_the_reason_and_the_detail(self, tmp_path: Path) -> None:
        """1695 runs died at 02:00 leaving only a stack trace behind."""
        target = tmp_path / "d.jsonl"
        record_run_aborted("no_display", "No usable X display.", log_file=target)
        (record,) = read_decisions(log_file=target)
        assert record["locked"] is None
        assert record["reason"] == "no_display"
        assert record["detail"] == "No usable X display."

    def test_it_is_loud(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Unlike the sync modes, this is never an expected outcome."""
        record_run_aborted(
            "no_display", "No usable X display.", log_file=tmp_path / "d"
        )
        assert any(r.levelname == "WARNING" for r in caplog.records)
