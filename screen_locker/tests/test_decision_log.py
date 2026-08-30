"""Tests for screen_locker._decision_log — the durable lock-decision trail.

This module exists because the 2026-08 enforcement outage left no evidence:
every skip logged at INFO on a path with no logging configured, so the journal
recorded thirteen days of nothing. These tests pin the two properties that make
that impossible to repeat -- a skip is loud, and every decision is written to a
file that outlives the journal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._decision_log import (
    DECISION_LOG_MAX_ENTRIES,
    LockDecision,
    read_decisions,
    record_decision,
)

if TYPE_CHECKING:
    import pytest


_PKG = "screen_locker._decision_log"


class TestLockDecisionRendering:
    """The one-line summary must stay greppable and complete."""

    def test_skip_line_reports_reason_and_weekly_progress(self) -> None:
        """A skip renders lock=no plus the counts that justify it."""
        line = LockDecision(
            locked=False,
            reason="early_bird_window_active",
            weekly_count=0,
            weekly_required=5,
        ).as_line()
        assert "DECISION" in line
        assert "lock=no" in line
        assert "reason=early_bird_window_active" in line
        assert "weekly=0/5" in line

    def test_enforced_line_reports_lock_yes(self) -> None:
        """An enforced run renders lock=yes."""
        assert "lock=yes" in LockDecision(locked=True, reason="enforced").as_line()

    def test_extra_fields_and_detail_are_rendered(self) -> None:
        """Extra context and the human detail both reach the line."""
        line = LockDecision(
            locked=False,
            reason="heat_skip",
            detail="too hot",
            extra={"temp_celsius": 34.0},
        ).as_line()
        assert "temp_celsius=34.0" in line
        assert "too hot" in line

    def test_weekly_is_omitted_when_unknown(self) -> None:
        """No weekly counts → no misleading 'weekly=None/None'."""
        assert "weekly=" not in LockDecision(locked=True, reason="enforced").as_line()


class TestRecordDecision:
    """Recording must be loud for skips and durable for everything."""

    def test_skip_is_logged_at_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A decision NOT to enforce must be visible at warning.

        This is the exact regression: an INFO-level skip is invisible under the
        default logging configuration and hid the outage for thirteen days.
        """
        with caplog.at_level("INFO"):
            record_decision(
                LockDecision(locked=False, reason="weekly_minimum_met"),
                log_file=tmp_path / "d.jsonl",
            )
        record = next(r for r in caplog.records if "DECISION" in r.message)
        assert record.levelname == "WARNING"

    def test_enforced_is_logged_at_info(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An enforced lock is self-evident on screen, so INFO suffices."""
        with caplog.at_level("INFO"):
            record_decision(
                LockDecision(locked=True, reason="enforced"),
                log_file=tmp_path / "d.jsonl",
            )
        record = next(r for r in caplog.records if "DECISION" in r.message)
        assert record.levelname == "INFO"

    def test_decision_is_appended_to_the_durable_trail(self, tmp_path: Path) -> None:
        """Each decision lands in the file as one JSON object."""
        target = tmp_path / "d.jsonl"
        record_decision(
            LockDecision(
                locked=False, reason="sick_day", weekly_count=2, weekly_required=5
            ),
            log_file=target,
        )
        record_decision(LockDecision(locked=True, reason="enforced"), log_file=target)
        records = read_decisions(log_file=target)
        assert [r["reason"] for r in records] == ["sick_day", "enforced"]
        assert records[0]["weekly_count"] == 2
        assert records[0]["locked"] is False
        assert "timestamp" in records[0]

    def test_parent_directory_is_created(self, tmp_path: Path) -> None:
        """A missing data directory is created rather than losing the record."""
        target = tmp_path / "nested" / "deeper" / "d.jsonl"
        record_decision(LockDecision(locked=True, reason="enforced"), log_file=target)
        assert target.exists()

    def test_history_is_trimmed_to_the_cap(self, tmp_path: Path) -> None:
        """An every-30-minutes timer must not grow the trail without bound."""
        target = tmp_path / "d.jsonl"
        target.write_text(
            "\n".join(
                json.dumps({"reason": f"old{i}"})
                for i in range(DECISION_LOG_MAX_ENTRIES + 50)
            )
            + "\n"
        )
        record_decision(LockDecision(locked=True, reason="newest"), log_file=target)
        records = read_decisions(log_file=target)
        assert len(records) == DECISION_LOG_MAX_ENTRIES
        assert records[-1]["reason"] == "newest"

    def test_write_failure_is_reported_not_swallowed(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A trail that cannot be written says so — a gap must be visible."""
        target = tmp_path / "d.jsonl"
        with (
            patch.object(Path, "write_text", side_effect=OSError("disk full")),
            caplog.at_level("WARNING"),
        ):
            record_decision(
                LockDecision(locked=True, reason="enforced"), log_file=target
            )
        assert any("decision log" in r.message for r in caplog.records)

    def test_write_failure_does_not_stop_the_locker(self, tmp_path: Path) -> None:
        """Failing to record must never prevent the lock from happening."""
        with patch.object(Path, "write_text", side_effect=OSError("nope")):
            record_decision(
                LockDecision(locked=True, reason="enforced"),
                log_file=tmp_path / "d.jsonl",
            )


class TestReadDecisions:
    """Reading must degrade gracefully, never crash an investigation."""

    def test_missing_file_returns_empty_and_says_so(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No history yet is normal, but is still stated out loud."""
        with caplog.at_level("WARNING"):
            assert read_decisions(log_file=tmp_path / "nope.jsonl") == []
        assert any("No decision log" in r.message for r in caplog.records)

    def test_unreadable_file_is_reported(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An OSError is surfaced rather than silently returning []."""
        target = tmp_path / "d.jsonl"
        target.write_text("{}\n")
        with (
            patch.object(Path, "read_text", side_effect=OSError("locked")),
            caplog.at_level("WARNING"),
        ):
            assert read_decisions(log_file=target) == []
        assert any("Could not read" in r.message for r in caplog.records)

    def test_corrupt_lines_are_skipped_not_fatal(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A damaged trail still yields its readable records."""
        target = tmp_path / "d.jsonl"
        target.write_text('{"reason": "good"}\nnot json at all\n\n')
        with caplog.at_level("WARNING"):
            records = read_decisions(log_file=target)
        assert [r["reason"] for r in records] == ["good"]
        assert any("corrupt" in r.message for r in caplog.records)

    def test_non_object_lines_are_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A bare JSON scalar is not a decision record."""
        target = tmp_path / "d.jsonl"
        target.write_text('[1, 2, 3]\n{"reason": "good"}\n')
        with caplog.at_level("WARNING"):
            records = read_decisions(log_file=target)
        assert [r["reason"] for r in records] == ["good"]
        assert any("not an object" in r.message for r in caplog.records)
