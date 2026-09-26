"""Tests for the LeetCode shutdown hour: reading the ledger, failing closed.

Entries are signed against a temp key with gatelock's own ``compute_entry_hmac``
so a forged credit and a genuine one differ in exactly the way they do on the
machine.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from gatelock.log_integrity import compute_entry_hmac
import pytest

from screen_locker import _leetcode_bonus
from screen_locker._leetcode_bonus import (
    LEETCODE_BONUS_HOURS,
    leetcode_bonus_hours,
    leetcode_solved_today,
)

if TYPE_CHECKING:
    from pathlib import Path

_NOW = datetime(2026, 9, 15, 14, 0).astimezone()


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"test-key-bytes")
    with patch.object(_leetcode_bonus, "HMAC_KEY_FILE", key):
        yield key


def _entry(
    kind: str, *, submitted_at: object, key: Path, day: str = "2026-09-15"
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "entry_id": f"{kind}:{submitted_at}",
        "kind": kind,
        "day": day,
        "detail": {"submitted_at": submitted_at},
    }
    return {**body, "hmac": compute_entry_hmac(body, key_file=key)}


def _ledger(tmp_path: Path, entries: list[Any]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"entries": entries}))
    return path


class TestSolvedToday:
    def test_verified_credit_today_is_solved(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        stamp = (_NOW - timedelta(hours=2)).timestamp()
        ledger = _ledger(tmp_path, [_entry("credit", submitted_at=stamp, key=key_file)])
        assert leetcode_solved_today(ledger, now=_NOW) is True

    def test_credit_from_yesterday_is_not_solved(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        """A 23:50 solve harvested this morning counts for yesterday, never today."""
        stamp = (_NOW - timedelta(days=1)).timestamp()
        ledger = _ledger(tmp_path, [_entry("credit", submitted_at=stamp, key=key_file)])
        assert leetcode_solved_today(ledger, now=_NOW) is False

    def test_seen_and_charge_entries_never_count(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        stamp = _NOW.timestamp()
        ledger = _ledger(
            tmp_path,
            [
                _entry("seen", submitted_at=stamp, key=key_file),
                _entry("charge", submitted_at=stamp, key=key_file),
                "not-a-dict",
            ],
        )
        assert leetcode_solved_today(ledger, now=_NOW) is False

    def test_forged_credit_is_ignored(self, tmp_path: Path, key_file: Path) -> None:
        entry = _entry("credit", submitted_at=_NOW.timestamp(), key=key_file)
        entry["detail"]["submitted_at"] = (
            _NOW.timestamp() - 1
        )  # body no longer matches hmac
        ledger = _ledger(tmp_path, [entry])
        assert leetcode_solved_today(ledger, now=_NOW) is False

    def test_unparsable_submitted_at_falls_back_to_day_key(
        self, tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        ledger = _ledger(
            tmp_path,
            [
                _entry(
                    "credit",
                    submitted_at="soon",
                    key=key_file,
                    day=_NOW.date().isoformat(),
                )
            ],
        )
        with caplog.at_level(logging.WARNING):
            assert leetcode_solved_today(ledger, now=_NOW) is True
        assert "unparsable submitted_at" in caplog.text

    def test_missing_submitted_at_uses_day_key(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        body: dict[str, Any] = {"entry_id": "x", "kind": "credit", "day": "2000-01-01"}
        entry = {**body, "hmac": compute_entry_hmac(body, key_file=key_file)}
        assert leetcode_solved_today(_ledger(tmp_path, [entry]), now=_NOW) is False

    def test_resolves_module_path_when_none_given(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        stamp = _NOW.timestamp()
        ledger = _ledger(tmp_path, [_entry("credit", submitted_at=stamp, key=key_file)])
        with patch.object(_leetcode_bonus, "LEETCODE_LEDGER_FILE", ledger):
            assert leetcode_solved_today(now=_NOW) is True


class TestCannotCheck:
    """Every unreadable state is None -- never a confident False."""

    def test_missing_ledger(self, tmp_path: Path, key_file: Path) -> None:
        assert leetcode_solved_today(tmp_path / "missing.json") is None

    def test_invalid_json(self, tmp_path: Path, key_file: Path) -> None:
        path = tmp_path / "ledger.json"
        path.write_text("{not json")
        assert leetcode_solved_today(path) is None

    def test_no_entries_array(self, tmp_path: Path, key_file: Path) -> None:
        path = tmp_path / "ledger.json"
        path.write_text(json.dumps({"entries": "nope"}))
        assert leetcode_solved_today(path) is None

    def test_unreadable_key(self, tmp_path: Path) -> None:
        with patch.object(_leetcode_bonus, "HMAC_KEY_FILE", tmp_path / "no.key"):
            assert leetcode_solved_today(_ledger(tmp_path, [])) is None

    def test_empty_key(self, tmp_path: Path) -> None:
        key = tmp_path / "hmac.key"
        key.write_bytes(b"  \n")
        with patch.object(_leetcode_bonus, "HMAC_KEY_FILE", key):
            assert leetcode_solved_today(_ledger(tmp_path, [])) is None


class TestBonusHours:
    def test_solved_earns_the_hour(self) -> None:
        with patch.object(_leetcode_bonus, "leetcode_solved_today", return_value=True):
            assert leetcode_bonus_hours() == LEETCODE_BONUS_HOURS

    def test_not_solved_earns_nothing(self) -> None:
        with patch.object(_leetcode_bonus, "leetcode_solved_today", return_value=False):
            assert leetcode_bonus_hours() == 0

    def test_cannot_check_fails_closed_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch.object(_leetcode_bonus, "leetcode_solved_today", return_value=None),
            caplog.at_level(logging.WARNING),
        ):
            assert leetcode_bonus_hours() == 0
        assert "could not be checked" in caplog.text


class TestReadEntriesLabel:
    """_read_entries is shared with book-guard's reader; the label names whose."""

    def test_default_label_is_leetcode(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            assert _leetcode_bonus._read_entries(tmp_path / "missing.json") is None
        assert "Cannot read the LeetCode ledger" in caplog.text

    def test_custom_label_names_the_ledger(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "ledger.json"
        path.write_text(json.dumps({"no": "entries"}))
        with caplog.at_level(logging.WARNING):
            assert _leetcode_bonus._read_entries(path, "book-guard") is None
        assert "book-guard ledger at" in caplog.text
        assert "LeetCode" not in caplog.text
