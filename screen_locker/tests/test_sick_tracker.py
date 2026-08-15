"""Tests for the sick-day tracker pure-logic module."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker import _sick_tracker
from screen_locker._constants import (
    SICK_BUDGET_PER_7_DAYS,
    SICK_BUDGET_PER_30_DAYS,
    SICK_BUDGET_PER_90_DAYS,
    SICK_COMMITMENT_PENALTY_DAYS,
    SICK_LOCKOUT_MULTIPLIER_PER_RECENT,
    SICK_LOCKOUT_SECONDS,
)
from screen_locker._sick_tracker import (
    SickHistory,
    add_sick_day,
    budget_summary,
    clear_one_debt,
    compute_lockout_seconds,
    count_in_window,
    is_budget_exhausted,
    load_history,
    save_history,
)

if TYPE_CHECKING:
    from pathlib import Path


_TODAY = "2026-05-10"


class TestLoadHistory:
    """Tests for load_history."""

    def test_returns_empty_when_file_missing(self) -> None:
        """Returns empty when file missing."""
        history = load_history()
        assert history == SickHistory()

    def test_reads_existing_file(self, tmp_path: Path) -> None:
        """Reads existing file."""
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
        """Returns empty on corrupt JSON."""
        target = tmp_path / "sick_history.json"
        target.write_text("not json")
        with patch.object(_sick_tracker, "SICK_HISTORY_FILE", target):
            assert load_history() == SickHistory()

    def test_returns_empty_on_oserror(self, tmp_path: Path) -> None:
        """Returns empty on oserror."""
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
        """Persists history."""
        target = tmp_path / "sick_history.json"
        with patch.object(_sick_tracker, "SICK_HISTORY_FILE", target):
            history = SickHistory(sick_days=["2026-05-01"], debt=1)
            assert save_history(history) is True
            reloaded = load_history()
        assert reloaded == history

    def test_returns_false_on_oserror(self, tmp_path: Path) -> None:
        """Returns false on oserror."""
        target = tmp_path / "missing_dir" / "sick_history.json"
        with patch.object(_sick_tracker, "SICK_HISTORY_FILE", target):
            assert save_history(SickHistory()) is False


class TestCountInWindow:
    """Tests for count_in_window."""

    def test_counts_only_within_window(self) -> None:
        """Counts only within window."""
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
        """Skips invalid date strings."""
        history = SickHistory(sick_days=["bad-date", "2026-05-09"])
        assert count_in_window(history, 7, today=_TODAY) == 1

    def test_returns_zero_when_today_invalid(self) -> None:
        """Returns zero when today invalid."""
        history = SickHistory(sick_days=["2026-05-09"])
        assert count_in_window(history, 7, today="bogus") == 0

    def test_uses_today_default_when_none(self) -> None:
        """Uses today default when none."""
        history = SickHistory(sick_days=[])
        assert count_in_window(history, 7) == 0


class TestIsBudgetExhausted:
    """Tests for is_budget_exhausted."""

    def test_false_when_under_budget(self) -> None:
        """False when under budget."""
        assert is_budget_exhausted(SickHistory(), today=_TODAY) is False

    def test_true_when_weekly_exhausted(self) -> None:
        """True when weekly exhausted."""
        history = SickHistory(
            sick_days=["2026-05-09"] * SICK_BUDGET_PER_7_DAYS,
        )
        assert is_budget_exhausted(history, today=_TODAY) is True

    def test_true_when_monthly_exhausted(self) -> None:
        # Spread far enough apart to all be in 30d but not 7d.
        """True when monthly exhausted."""
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
        """True when quarterly exhausted."""
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
        """Base when no recent."""
        assert (
            compute_lockout_seconds(SickHistory(), today=_TODAY) == SICK_LOCKOUT_SECONDS
        )

    def test_doubles_per_recent(self) -> None:
        """Doubles per recent."""
        history = SickHistory(sick_days=["2026-05-09", "2026-04-20"])
        recent = 2  # both within 30d
        expected = SICK_LOCKOUT_SECONDS * (SICK_LOCKOUT_MULTIPLIER_PER_RECENT**recent)
        assert compute_lockout_seconds(history, today=_TODAY) == expected


class TestBudgetSummary:
    """Tests for budget_summary."""

    def test_renders_all_windows_and_debt(self) -> None:
        """Renders all windows and debt."""
        history = SickHistory(sick_days=["2026-05-09"], debt=3)
        summary = budget_summary(history, today=_TODAY)
        assert "Sick:" in summary
        assert "1/" in summary
        assert "Debt: 3" in summary


class TestAddSickDay:
    """Tests for add_sick_day."""

    def test_adds_today_and_increments_debt(self) -> None:
        """Adds today and increments debt."""
        history = SickHistory()
        new_debt = add_sick_day(history, today=_TODAY)
        assert history.sick_days == [_TODAY]
        assert new_debt == 1

    def test_idempotent_on_same_day(self) -> None:
        """Idempotent on same day."""
        history = SickHistory(sick_days=[_TODAY], debt=0)
        new_debt = add_sick_day(history, today=_TODAY)
        assert history.sick_days == [_TODAY]
        # Debt still increments by 1 even if the date is already present.
        assert new_debt == 1

    def test_double_penalty_when_commitment_broken(self) -> None:
        """Double penalty when commitment broken."""
        history = SickHistory(broken_commitments=[_TODAY])
        new_debt = add_sick_day(history, today=_TODAY)
        assert new_debt == SICK_COMMITMENT_PENALTY_DAYS


class TestClearOneDebt:
    """Tests for clear_one_debt."""

    def test_decrements_when_positive(self) -> None:
        """Decrements when positive."""
        history = SickHistory(debt=2)
        assert clear_one_debt(history) == 1
        assert history.debt == 1

    def test_clamped_at_zero(self) -> None:
        """Clamped at zero."""
        history = SickHistory(debt=0)
        assert clear_one_debt(history) == 0
