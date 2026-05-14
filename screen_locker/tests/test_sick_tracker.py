"""Tests for the sick-day tracker pure-logic module."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from python_pkg.screen_locker import _sick_tracker
from python_pkg.screen_locker._constants import (
    SICK_BUDGET_PER_7_DAYS,
    SICK_BUDGET_PER_30_DAYS,
    SICK_BUDGET_PER_90_DAYS,
    SICK_COMMITMENT_PENALTY_DAYS,
    SICK_HISTORY_REVIEW_COUNT,
    SICK_JUSTIFICATION_MIN_CHARS,
    SICK_LOCKOUT_MULTIPLIER_PER_RECENT,
    SICK_LOCKOUT_SECONDS,
)
from python_pkg.screen_locker._sick_tracker import (
    JustificationDraft,
    SickHistory,
    add_justification,
    add_sick_day,
    budget_summary,
    clear_one_debt,
    compute_lockout_seconds,
    count_in_window,
    format_recent_justifications,
    had_commitment_for_today,
    is_budget_exhausted,
    load_history,
    mark_commitment_broken,
    recent_justifications,
    record_commitment_for_tomorrow,
    save_history,
    validate_justification,
)

if TYPE_CHECKING:
    from pathlib import Path


_TODAY = "2026-05-10"


class TestLoadHistory:
    """Tests for load_history."""

    def test_returns_empty_when_file_missing(self) -> None:
        history = load_history()
        assert history == SickHistory()

    def test_reads_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "sick_history.json"
        target.write_text(
            '{"sick_days": ["2026-05-01"], "debt": 2,'
            ' "commitments": {"2026-05-10": true},'
            ' "broken_commitments": ["2026-05-09"],'
            ' "justifications": [{"date": "2026-05-01"}]}'
        )
        with patch.object(_sick_tracker, "SICK_HISTORY_FILE", target):
            history = load_history()
        assert history.sick_days == ["2026-05-01"]
        assert history.debt == 2
        assert history.commitments == {"2026-05-10": True}
        assert history.broken_commitments == ["2026-05-09"]
        assert history.justifications == [{"date": "2026-05-01"}]

    def test_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        target = tmp_path / "sick_history.json"
        target.write_text("not json")
        with patch.object(_sick_tracker, "SICK_HISTORY_FILE", target):
            assert load_history() == SickHistory()

    def test_returns_empty_on_oserror(self, tmp_path: Path) -> None:
        target = tmp_path / "sick_history.json"
        target.write_text("{}")
        with (
            patch.object(_sick_tracker, "SICK_HISTORY_FILE", target),
            patch.object(type(target), "open", side_effect=OSError("boom")),
        ):
            assert load_history() == SickHistory()


class TestSaveHistory:
    """Tests for save_history."""

    def test_persists_history(self, tmp_path: Path) -> None:
        target = tmp_path / "sick_history.json"
        with patch.object(_sick_tracker, "SICK_HISTORY_FILE", target):
            history = SickHistory(sick_days=["2026-05-01"], debt=1)
            assert save_history(history) is True
            reloaded = load_history()
        assert reloaded == history

    def test_returns_false_on_oserror(self, tmp_path: Path) -> None:
        target = tmp_path / "missing_dir" / "sick_history.json"
        with patch.object(_sick_tracker, "SICK_HISTORY_FILE", target):
            assert save_history(SickHistory()) is False


class TestCountInWindow:
    """Tests for count_in_window."""

    def test_counts_only_within_window(self) -> None:
        history = SickHistory(
            sick_days=[
                "2026-05-09",  # 1 day ago: in 7d, 30d, 90d
                "2026-05-03",  # 7 days ago: NOT in 7d (cutoff exclusive)
                "2026-04-25",  # 15 days ago: NOT in 7d, in 30d, 90d
                "2026-01-01",  # ~130 days ago: outside 90d
            ],
        )
        assert count_in_window(history, 7, today=_TODAY) == 1
        assert count_in_window(history, 30, today=_TODAY) == 3
        assert count_in_window(history, 90, today=_TODAY) == 3

    def test_skips_invalid_date_strings(self) -> None:
        history = SickHistory(sick_days=["bad-date", "2026-05-09"])
        assert count_in_window(history, 7, today=_TODAY) == 1

    def test_returns_zero_when_today_invalid(self) -> None:
        history = SickHistory(sick_days=["2026-05-09"])
        assert count_in_window(history, 7, today="bogus") == 0

    def test_uses_today_default_when_none(self) -> None:
        history = SickHistory(sick_days=[])
        assert count_in_window(history, 7) == 0


class TestIsBudgetExhausted:
    """Tests for is_budget_exhausted."""

    def test_false_when_under_budget(self) -> None:
        assert is_budget_exhausted(SickHistory(), today=_TODAY) is False

    def test_true_when_weekly_exhausted(self) -> None:
        history = SickHistory(
            sick_days=["2026-05-09"] * SICK_BUDGET_PER_7_DAYS,
        )
        assert is_budget_exhausted(history, today=_TODAY) is True

    def test_true_when_monthly_exhausted(self) -> None:
        # Spread far enough apart to all be in 30d but not 7d.
        history = SickHistory(
            sick_days=[
                "2026-05-08",
                "2026-04-28",
                "2026-04-18",
            ][:SICK_BUDGET_PER_30_DAYS],
        )
        assert is_budget_exhausted(history, today=_TODAY) is True

    def test_true_when_quarterly_exhausted(self) -> None:
        # All in 90d but only 1 in 30d.
        days = [
            "2026-05-09",
            "2026-04-01",
            "2026-03-15",
            "2026-03-10",
            "2026-03-05",
            "2026-03-01",
            "2026-02-28",
            "2026-02-25",
            "2026-02-20",
            "2026-02-15",
        ]
        history = SickHistory(sick_days=days[:SICK_BUDGET_PER_90_DAYS])
        assert is_budget_exhausted(history, today=_TODAY) is True


class TestComputeLockoutSeconds:
    """Tests for compute_lockout_seconds."""

    def test_base_when_no_recent(self) -> None:
        assert (
            compute_lockout_seconds(SickHistory(), today=_TODAY) == SICK_LOCKOUT_SECONDS
        )

    def test_doubles_per_recent(self) -> None:
        history = SickHistory(sick_days=["2026-05-09", "2026-04-20"])
        recent = 2  # both within 30d
        expected = SICK_LOCKOUT_SECONDS * (SICK_LOCKOUT_MULTIPLIER_PER_RECENT**recent)
        assert compute_lockout_seconds(history, today=_TODAY) == expected


class TestBudgetSummary:
    """Tests for budget_summary."""

    def test_renders_all_windows_and_debt(self) -> None:
        history = SickHistory(sick_days=["2026-05-09"], debt=3)
        summary = budget_summary(history, today=_TODAY)
        assert "Sick:" in summary
        assert "1/" in summary
        assert "Debt: 3" in summary


class TestAddSickDay:
    """Tests for add_sick_day."""

    def test_adds_today_and_increments_debt(self) -> None:
        history = SickHistory()
        new_debt = add_sick_day(history, today=_TODAY)
        assert history.sick_days == [_TODAY]
        assert new_debt == 1

    def test_idempotent_on_same_day(self) -> None:
        history = SickHistory(sick_days=[_TODAY], debt=0)
        new_debt = add_sick_day(history, today=_TODAY)
        assert history.sick_days == [_TODAY]
        # Debt still increments by 1 even if the date is already present.
        assert new_debt == 1

    def test_double_penalty_when_commitment_broken(self) -> None:
        history = SickHistory(broken_commitments=[_TODAY])
        new_debt = add_sick_day(history, today=_TODAY)
        assert new_debt == SICK_COMMITMENT_PENALTY_DAYS


class TestClearOneDebt:
    """Tests for clear_one_debt."""

    def test_decrements_when_positive(self) -> None:
        history = SickHistory(debt=2)
        assert clear_one_debt(history) == 1
        assert history.debt == 1

    def test_clamped_at_zero(self) -> None:
        history = SickHistory(debt=0)
        assert clear_one_debt(history) == 0


class TestRecordCommitment:
    """Tests for record_commitment_for_tomorrow + had_commitment_for_today."""

    def test_records_for_tomorrow(self) -> None:
        history = SickHistory()
        result = record_commitment_for_tomorrow(history, today=_TODAY)
        assert result == "2026-05-11"
        assert history.commitments["2026-05-11"] is True

    def test_returns_today_when_today_invalid(self) -> None:
        history = SickHistory()
        result = record_commitment_for_tomorrow(history, today="bogus")
        assert result == "bogus"
        assert history.commitments == {}

    def test_had_commitment_returns_true(self) -> None:
        history = SickHistory(commitments={_TODAY: True})
        assert had_commitment_for_today(history, today=_TODAY) is True

    def test_had_commitment_returns_false(self) -> None:
        assert had_commitment_for_today(SickHistory(), today=_TODAY) is False


class TestMarkCommitmentBroken:
    """Tests for mark_commitment_broken."""

    def test_appends_when_committed(self) -> None:
        history = SickHistory(commitments={_TODAY: True})
        mark_commitment_broken(history, today=_TODAY)
        assert history.broken_commitments == [_TODAY]

    def test_idempotent(self) -> None:
        history = SickHistory(commitments={_TODAY: True}, broken_commitments=[_TODAY])
        mark_commitment_broken(history, today=_TODAY)
        assert history.broken_commitments == [_TODAY]

    def test_noop_when_no_commitment(self) -> None:
        history = SickHistory()
        mark_commitment_broken(history, today=_TODAY)
        assert history.broken_commitments == []


class TestValidateJustification:
    """Tests for validate_justification."""

    def _good_text(self) -> str:
        return "x" * SICK_JUSTIFICATION_MIN_CHARS

    def _draft(
        self,
        *,
        symptom: str | None = None,
        onset: str | None = None,
        severity: int | None = None,
        text: str | None = None,
    ) -> JustificationDraft:
        return JustificationDraft(
            symptom="fever" if symptom is None else symptom,
            onset="last night" if onset is None else onset,
            severity=7 if severity is None else severity,
            text=self._good_text() if text is None else text,
        )

    def test_returns_none_when_valid(self) -> None:
        assert validate_justification(self._draft()) is None

    def test_rejects_blank_symptom(self) -> None:
        assert validate_justification(self._draft(symptom="   ")) is not None

    def test_rejects_blank_onset(self) -> None:
        assert validate_justification(self._draft(onset="")) is not None

    @pytest.mark.parametrize("severity", [0, 11, -1])
    def test_rejects_severity_out_of_range(self, severity: int) -> None:
        assert validate_justification(self._draft(severity=severity)) is not None

    def test_rejects_short_text(self) -> None:
        assert validate_justification(self._draft(text="too short")) is not None


class TestAddJustification:
    """Tests for add_justification."""

    def _draft(self, text: str = "  full description text  ") -> JustificationDraft:
        return JustificationDraft(
            symptom="fever",
            onset="last night",
            severity=7,
            text=text,
        )

    def test_appends_entry_with_hmac_when_key_present(self) -> None:
        history = SickHistory()
        with patch.object(_sick_tracker, "compute_entry_hmac", return_value="deadbeef"):
            entry = add_justification(history, self._draft(), today=_TODAY)
        assert history.justifications == [entry]
        assert entry["hmac"] == "deadbeef"
        assert entry["text"] == "full description text"
        assert entry["symptom"] == "fever"
        assert entry["severity"] == 7
        assert entry["date"] == _TODAY

    def test_omits_hmac_when_key_unavailable(self) -> None:
        history = SickHistory()
        with patch.object(_sick_tracker, "compute_entry_hmac", return_value=None):
            entry = add_justification(
                history,
                self._draft(text="full description"),
                today=_TODAY,
            )
        assert "hmac" not in entry


class TestRecentJustifications:
    """Tests for recent_justifications + format_recent_justifications."""

    def test_returns_last_n(self) -> None:
        history = SickHistory(
            justifications=[{"i": i} for i in range(5)],
        )
        assert recent_justifications(history, 2) == [{"i": 3}, {"i": 4}]

    def test_returns_empty_list_when_n_zero(self) -> None:
        history = SickHistory(justifications=[{"i": 0}])
        assert recent_justifications(history, 0) == []

    def test_default_n_is_review_count(self) -> None:
        history = SickHistory(
            justifications=[{"i": i} for i in range(SICK_HISTORY_REVIEW_COUNT + 5)],
        )
        assert len(recent_justifications(history)) == SICK_HISTORY_REVIEW_COUNT

    def test_format_returns_empty_when_no_history(self) -> None:
        assert format_recent_justifications(SickHistory()) == ""

    def test_format_renders_lines(self) -> None:
        history = SickHistory(
            justifications=[
                {"date": "2026-05-01", "symptom": "fever", "severity": 7},
                {"date": "2026-04-15", "symptom": "headache", "severity": 4},
            ],
        )
        out = format_recent_justifications(history)
        assert "2026-05-01" in out
        assert "fever" in out
        assert "headache" in out

    def test_format_handles_missing_fields(self) -> None:
        history = SickHistory(justifications=[{}])
        out = format_recent_justifications(history)
        assert "?" in out
