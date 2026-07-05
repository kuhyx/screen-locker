"""Tests for the pure, read-only predicates in _compliance_state.py."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker import _compliance_state
from screen_locker._compliance_state import (
    AutoUpgradeOpportunity,
    describe_auto_upgrade_opportunity,
    has_logged_today,
    is_early_bird_pending,
    is_scheduled_skip_today,
    is_sick_day_today,
)
from screen_locker._sick_tracker import SickHistory

if TYPE_CHECKING:
    from pathlib import Path


def _today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


class TestIsScheduledSkipToday:
    """Mirrors test_scheduled_skip.py's coverage, for the standalone function."""

    def test_missing_file(self, tmp_path: Path) -> None:
        assert is_scheduled_skip_today(tmp_path / "skips.json") is False

    def test_today_listed(self, tmp_path: Path) -> None:
        skip_file = tmp_path / "skips.json"
        skip_file.write_text(json.dumps([_today()]))
        assert is_scheduled_skip_today(skip_file) is True

    def test_today_not_listed(self, tmp_path: Path) -> None:
        skip_file = tmp_path / "skips.json"
        skip_file.write_text(json.dumps(["1999-01-01"]))
        assert is_scheduled_skip_today(skip_file) is False

    def test_corrupt_json(self, tmp_path: Path) -> None:
        skip_file = tmp_path / "skips.json"
        skip_file.write_text("{bad}")
        assert is_scheduled_skip_today(skip_file) is False

    def test_explicit_today_override(self, tmp_path: Path) -> None:
        skip_file = tmp_path / "skips.json"
        skip_file.write_text(json.dumps(["2020-05-05"]))
        assert is_scheduled_skip_today(skip_file, today="2020-05-05") is True


class TestHasLoggedToday:
    """Mirrors test_init_and_log.py's HMAC branches, for the standalone function."""

    def test_missing_file(self, tmp_path: Path) -> None:
        assert has_logged_today(tmp_path / "log.json") is False

    def test_corrupt_json(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text("{bad}")
        assert has_logged_today(log_file) is False

    def test_no_entry_for_today(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({"1999-01-01": {}}))
        assert has_logged_today(log_file) is False

    def test_valid_hmac(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {"hmac": "sig"}}))
        with patch(
            "screen_locker._compliance_state.verify_entry_hmac", return_value=True
        ):
            assert has_logged_today(log_file) is True

    def test_unsigned_accepted_when_key_unavailable(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {}}))
        with (
            patch(
                "screen_locker._compliance_state.verify_entry_hmac", return_value=False
            ),
            patch(
                "screen_locker._compliance_state.compute_entry_hmac", return_value=None
            ),
        ):
            assert has_logged_today(log_file) is True

    def test_rejected_when_key_available(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {}}))
        with (
            patch(
                "screen_locker._compliance_state.verify_entry_hmac", return_value=False
            ),
            patch(
                "screen_locker._compliance_state.compute_entry_hmac", return_value="sig"
            ),
        ):
            assert has_logged_today(log_file) is False

    def test_rejected_when_signed_but_invalid(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({_today(): {"hmac": "tampered"}}))
        with (
            patch(
                "screen_locker._compliance_state.verify_entry_hmac", return_value=False
            ),
            patch(
                "screen_locker._compliance_state.compute_entry_hmac", return_value=None
            ),
        ):
            assert has_logged_today(log_file) is False


class TestIsEarlyBirdPending:
    """Mirrors test_early_bird.py's HMAC branches, for the standalone function."""

    def test_missing_file(self, tmp_path: Path) -> None:
        assert is_early_bird_pending(tmp_path / "pending.json") is False

    def test_corrupt_json(self, tmp_path: Path) -> None:
        pending_file = tmp_path / "pending.json"
        pending_file.write_text("{bad}")
        assert is_early_bird_pending(pending_file) is False

    def test_not_a_dict(self, tmp_path: Path) -> None:
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps(["not", "a", "dict"]))
        assert is_early_bird_pending(pending_file) is False

    def test_stale_date(self, tmp_path: Path) -> None:
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": "2000-01-01", "hmac": "sig"}))
        assert is_early_bird_pending(pending_file) is False

    def test_valid_hmac(self, tmp_path: Path) -> None:
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today(), "hmac": "sig"}))
        with patch(
            "screen_locker._compliance_state.verify_entry_hmac", return_value=True
        ):
            assert is_early_bird_pending(pending_file) is True

    def test_unsigned_accepted_when_key_unavailable(self, tmp_path: Path) -> None:
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today()}))
        with (
            patch(
                "screen_locker._compliance_state.verify_entry_hmac", return_value=False
            ),
            patch(
                "screen_locker._compliance_state.compute_entry_hmac", return_value=None
            ),
        ):
            assert is_early_bird_pending(pending_file) is True

    def test_rejected_when_key_available(self, tmp_path: Path) -> None:
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today()}))
        with (
            patch(
                "screen_locker._compliance_state.verify_entry_hmac", return_value=False
            ),
            patch(
                "screen_locker._compliance_state.compute_entry_hmac", return_value="sig"
            ),
        ):
            assert is_early_bird_pending(pending_file) is False

    def test_rejected_when_signed_but_invalid(self, tmp_path: Path) -> None:
        pending_file = tmp_path / "pending.json"
        pending_file.write_text(json.dumps({"date": _today(), "hmac": "bad"}))
        with (
            patch(
                "screen_locker._compliance_state.verify_entry_hmac", return_value=False
            ),
            patch(
                "screen_locker._compliance_state.compute_entry_hmac", return_value=None
            ),
        ):
            assert is_early_bird_pending(pending_file) is False


class TestIsSickDayToday:
    """Thin wrapper around _sick_tracker.is_sick_day."""

    def test_true_when_listed(self) -> None:
        history = SickHistory(sick_days=[_today()])
        assert is_sick_day_today(history) is True

    def test_false_when_not_listed(self) -> None:
        history = SickHistory(sick_days=["1999-01-01"])
        assert is_sick_day_today(history) is False

    def test_explicit_today_override(self) -> None:
        history = SickHistory(sick_days=["2020-05-05"])
        assert is_sick_day_today(history, today="2020-05-05") is True


class TestEarlyBirdWindowOpen:
    """Direct tests for the module-private, deliberately independent reimplementation."""

    def test_before_window(self) -> None:
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=299)
            is False
        )

    def test_at_start(self) -> None:
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=300)
            is True
        )

    def test_before_end(self) -> None:
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=509)
            is True
        )

    def test_at_end_exclusive(self) -> None:
        assert (
            _compliance_state._early_bird_window_open(extended=False, local_minutes=510)
            is False
        )

    def test_extended_before_end(self) -> None:
        assert (
            _compliance_state._early_bird_window_open(extended=True, local_minutes=539)
            is True
        )

    def test_extended_at_end_exclusive(self) -> None:
        assert (
            _compliance_state._early_bird_window_open(extended=True, local_minutes=540)
            is False
        )


class TestDescribeAutoUpgradeOpportunity:
    """The 3 possible outcomes: expired early-bird, sick day, or none."""

    def test_expired_early_bird(self) -> None:
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=True, early_bird_window_open=False, is_sick_day=False
        )
        assert result == AutoUpgradeOpportunity(
            would_attempt=True, via="early_bird_expired", reason=result.reason
        )

    def test_sick_day(self) -> None:
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=False, early_bird_window_open=False, is_sick_day=True
        )
        assert result.would_attempt is True
        assert result.via == "sick_day"

    def test_sick_day_takes_second_priority_when_pending_still_open(self) -> None:
        """pending+open doesn't count as expired, so sick_day is still checked."""
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=True, early_bird_window_open=True, is_sick_day=True
        )
        assert result.via == "sick_day"

    def test_none(self) -> None:
        result = describe_auto_upgrade_opportunity(
            early_bird_pending=False, early_bird_window_open=False, is_sick_day=False
        )
        assert result.would_attempt is False
        assert result.via == "none"
