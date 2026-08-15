"""Tests for the sick-day tracker pure-logic module."""
# pylint: disable=protected-access

from __future__ import annotations

from unittest.mock import patch

import pytest

from screen_locker import _sick_tracker
from screen_locker._constants import (
    SICK_HISTORY_REVIEW_COUNT,
    SICK_JUSTIFICATION_MIN_CHARS,
)
from screen_locker._sick_tracker import (
    JustificationDraft,
    SickHistory,
    add_justification,
    format_recent_justifications,
    had_commitment_for_today,
    mark_commitment_broken,
    recent_justifications,
    record_commitment_for_tomorrow,
    validate_justification,
)

_TODAY = "2026-05-10"


class TestRecordCommitment:
    """Tests for record_commitment_for_tomorrow + had_commitment_for_today."""

    def test_records_for_tomorrow(self) -> None:
        """Records for tomorrow."""
        history = SickHistory()
        result = record_commitment_for_tomorrow(history, today=_TODAY)
        assert result == "2026-05-11"
        assert history.commitments["2026-05-11"] is True

    def test_returns_today_when_today_invalid(self) -> None:
        """Returns today when today invalid."""
        history = SickHistory()
        result = record_commitment_for_tomorrow(history, today="bogus")
        assert result == "bogus"
        assert history.commitments == {}

    def test_had_commitment_returns_true(self) -> None:
        """Had commitment returns true."""
        history = SickHistory(commitments={_TODAY: True})
        assert had_commitment_for_today(history, today=_TODAY) is True

    def test_had_commitment_returns_false(self) -> None:
        """Had commitment returns false."""
        assert had_commitment_for_today(SickHistory(), today=_TODAY) is False


class TestMarkCommitmentBroken:
    """Tests for mark_commitment_broken."""

    def test_appends_when_committed(self) -> None:
        """Appends when committed."""
        history = SickHistory(commitments={_TODAY: True})
        mark_commitment_broken(history, today=_TODAY)
        assert history.broken_commitments == [_TODAY]

    def test_idempotent(self) -> None:
        """Idempotent."""
        history = SickHistory(commitments={_TODAY: True}, broken_commitments=[_TODAY])
        mark_commitment_broken(history, today=_TODAY)
        assert history.broken_commitments == [_TODAY]

    def test_noop_when_no_commitment(self) -> None:
        """Noop when no commitment."""
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
        """Returns none when valid."""
        assert validate_justification(self._draft()) is None

    def test_rejects_blank_symptom(self) -> None:
        """Rejects blank symptom."""
        assert validate_justification(self._draft(symptom="   ")) is not None

    def test_rejects_blank_onset(self) -> None:
        """Rejects blank onset."""
        assert validate_justification(self._draft(onset="")) is not None

    @pytest.mark.parametrize("severity", [0, 11, -1])
    def test_rejects_severity_out_of_range(self, severity: int) -> None:
        """Rejects severity out of range."""
        assert validate_justification(self._draft(severity=severity)) is not None

    def test_rejects_short_text(self) -> None:
        """Rejects short text."""
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
        """Appends entry with HMAC when key present."""
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
        """Omits HMAC when key unavailable."""
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
        """Returns last n."""
        history = SickHistory(
            justifications=[{"i": i} for i in range(5)],
        )
        assert recent_justifications(history, 2) == [{"i": 3}, {"i": 4}]

    def test_returns_empty_list_when_n_zero(self) -> None:
        """Returns empty list when n zero."""
        history = SickHistory(justifications=[{"i": 0}])
        assert recent_justifications(history, 0) == []

    def test_default_n_is_review_count(self) -> None:
        """Default n is review count."""
        history = SickHistory(
            justifications=[{"i": i} for i in range(SICK_HISTORY_REVIEW_COUNT + 5)],
        )
        assert len(recent_justifications(history)) == SICK_HISTORY_REVIEW_COUNT

    def test_format_returns_empty_when_no_history(self) -> None:
        """Format returns empty when no history."""
        assert format_recent_justifications(SickHistory()) == ""

    def test_format_renders_lines(self) -> None:
        """Format renders lines."""
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
        """Format handles missing fields."""
        history = SickHistory(justifications=[{}])
        out = format_recent_justifications(history)
        assert "?" in out
