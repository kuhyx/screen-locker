"""Tests for the pure, read-only predicates in _compliance_state.py."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._compliance_state import (
    has_logged_today,
    is_early_bird_pending,
    is_scheduled_skip_today,
    is_sick_day_today,
)
from screen_locker._sick_tracker import SickHistory

if TYPE_CHECKING:
    from pathlib import Path


def _today() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


class TestIsScheduledSkipToday:
    """Mirrors test_scheduled_skip.py's coverage, for the standalone function."""

    def test_missing_file(self, tmp_path: Path) -> None:
        """A missing skips file means today is not a scheduled skip."""
        assert is_scheduled_skip_today(tmp_path / "skips.json") is False

    def test_today_listed(self, tmp_path: Path) -> None:
        """Today's date in the skips list makes it a scheduled skip."""
        skip_file = tmp_path / "skips.json"
        skip_file.write_text(json.dumps([_today()]))
        assert is_scheduled_skip_today(skip_file) is True

    def test_today_not_listed(self, tmp_path: Path) -> None:
        """A list without today is not a scheduled skip."""
        skip_file = tmp_path / "skips.json"
        skip_file.write_text(json.dumps(["1999-01-01"]))
        assert is_scheduled_skip_today(skip_file) is False

    def test_corrupt_json(self, tmp_path: Path) -> None:
        """Unparsable JSON fails closed: not a skip."""
        skip_file = tmp_path / "skips.json"
        skip_file.write_text("{bad}")
        assert is_scheduled_skip_today(skip_file) is False

    def test_explicit_today_override(self, tmp_path: Path) -> None:
        """The `today` argument overrides the real date."""
        skip_file = tmp_path / "skips.json"
        skip_file.write_text(json.dumps(["2020-05-05"]))
        assert is_scheduled_skip_today(skip_file, today="2020-05-05") is True


class TestHasLoggedToday:
    """Mirrors test_init_and_log.py's HMAC branches, for the standalone function."""

    def test_missing_file(self, tmp_path: Path) -> None:
        """A missing log means nothing was logged today."""
        assert has_logged_today(tmp_path / "log.json") is False

    def test_corrupt_json(self, tmp_path: Path) -> None:
        """Unparsable JSON fails closed: nothing logged."""
        log_file = tmp_path / "log.json"
        log_file.write_text("{bad}")
        assert has_logged_today(log_file) is False

    def test_no_entry_for_today(self, tmp_path: Path) -> None:
        """An entry for another day does not count as today's."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({"1999-01-01": {}}))
        assert has_logged_today(log_file) is False

    def test_valid_hmac(self, tmp_path: Path) -> None:
        """A correctly signed entry for today counts."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {"hmac": "sig"}}))
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            assert has_logged_today(log_file) is True

    def test_unsigned_accepted_when_key_unavailable(self, tmp_path: Path) -> None:
        """With no HMAC key on the machine, an unsigned entry is accepted."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {}}))
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value=None,
            ),
        ):
            assert has_logged_today(log_file) is True

    def test_rejected_when_key_available(self, tmp_path: Path) -> None:
        """With a key available, an unsigned entry is rejected as tampering."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {}}))
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value="sig",
            ),
        ):
            assert has_logged_today(log_file) is False

    def test_rejected_when_signed_but_invalid(self, tmp_path: Path) -> None:
        """A signature that does not verify is rejected."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {"hmac": "tampered"}}))
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value=None,
            ),
        ):
            assert has_logged_today(log_file) is False


class TestIsEarlyBirdPending:
    """Mirrors test_early_bird.py's HMAC branches, for the standalone function."""

    def test_missing_file(self, tmp_path: Path) -> None:
        """A missing pending file means no early bird is pending."""
        assert is_early_bird_pending(tmp_path / "pending.json") is False

    def test_corrupt_json(self, tmp_path: Path) -> None:
        """Unparsable JSON fails closed: nothing pending."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text("{bad}")
        assert is_early_bird_pending(pending_file) is False

    def test_not_a_dict(self, tmp_path: Path) -> None:
        """A JSON list where a dict is expected fails closed."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps(["not", "a", "dict"]))
        assert is_early_bird_pending(pending_file) is False

    def test_stale_date(self, tmp_path: Path) -> None:
        """A pending record from an earlier day no longer applies."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": "2000-01-01", "hmac": "sig"}))
        assert is_early_bird_pending(pending_file) is False

    def test_valid_hmac(self, tmp_path: Path) -> None:
        """A correctly signed pending record for today counts."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today(), "hmac": "sig"}))
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            assert is_early_bird_pending(pending_file) is True

    def test_unsigned_accepted_when_key_unavailable(self, tmp_path: Path) -> None:
        """With no HMAC key, an unsigned pending record is accepted."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today()}))
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value=None,
            ),
        ):
            assert is_early_bird_pending(pending_file) is True

    def test_rejected_when_key_available(self, tmp_path: Path) -> None:
        """With a key available, an unsigned pending record is rejected."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today()}))
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value="sig",
            ),
        ):
            assert is_early_bird_pending(pending_file) is False

    def test_rejected_when_signed_but_invalid(self, tmp_path: Path) -> None:
        """A pending record whose signature fails to verify is rejected."""
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today(), "hmac": "bad"}))
        with (
            patch(
                "screen_locker._compliance_predicates.verify_entry_hmac",
                return_value=False,
            ),
            patch(
                "screen_locker._compliance_predicates.compute_entry_hmac",
                return_value=None,
            ),
        ):
            assert is_early_bird_pending(pending_file) is False


class TestIsSickDayToday:
    """Reading today's sick-day status out of the sick history."""

    """Thin wrapper around _sick_tracker.is_sick_day."""

    def test_true_when_listed(self) -> None:
        """Today present in the history is a sick day."""
        history = SickHistory(sick_days=[_today()])
        assert is_sick_day_today(history) is True

    def test_false_when_not_listed(self) -> None:
        """Today absent from the history is not a sick day."""
        history = SickHistory(sick_days=["1999-01-01"])
        assert is_sick_day_today(history) is False

    def test_explicit_today_override(self) -> None:
        """The `today` argument overrides the real date."""
        history = SickHistory(sick_days=["2020-05-05"])
        assert is_sick_day_today(history, today="2020-05-05") is True
