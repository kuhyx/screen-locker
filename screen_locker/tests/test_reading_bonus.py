"""Tests for the reading shutdown hour: reading book-guard's ledger, failing closed.

Rows are signed against a temp key with gatelock's own ``compute_entry_hmac``
so a forged credit and a genuine one differ in exactly the way they do on the
machine. The key is patched on ``_reading_bonus`` itself: the module holds its
own binding of ``HMAC_KEY_FILE``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from gatelock.log_integrity import compute_entry_hmac
import pytest

from screen_locker import _reading_bonus
from screen_locker._reading_bonus import (
    READING_BONUS_HOURS,
    read_today,
    reading_bonus_hours,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_NOW = datetime(2026, 10, 2, 21, 0).astimezone()


@pytest.fixture
def key_file(tmp_path: Path) -> Iterator[Path]:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"test-key-bytes")
    with patch.object(_reading_bonus, "HMAC_KEY_FILE", key):
        yield key


def _row(
    kind: str = "credit",
    *,
    key: Path,
    ended_at: object = None,
    bonus: str = "1",
    detail: object = None,
) -> dict[str, Any]:
    """One signed ledger row; ``detail`` overrides the default detail body."""
    if detail is None:
        stamp = _NOW - timedelta(hours=1) if ended_at is None else ended_at
        if isinstance(stamp, datetime):
            stamp = str(int(stamp.timestamp()))
        detail = {"bonus": bonus, "ended_at": stamp}
    body: dict[str, Any] = {"entry_id": f"{kind}:x", "kind": kind, "detail": detail}
    return {**body, "hmac": compute_entry_hmac(body, key_file=key)}


def _ledger(tmp_path: Path, entries: list[Any]) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"entries": entries}))
    return path


class TestReadToday:
    def test_verified_bonus_credit_read_today(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        ledger = _ledger(tmp_path, [_row(key=key_file)])
        assert read_today(ledger, now=_NOW) is True

    def test_missing_ledger_is_a_plain_false(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        """book-guard never ran: no reading, but no fault either."""
        assert read_today(tmp_path / "missing.json", now=_NOW) is False

    def test_session_ended_yesterday_does_not_count(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        """Read at 22:30, quizzed next morning: earns the evening, not today."""
        row = _row(key=key_file, ended_at=_NOW - timedelta(days=1))
        assert read_today(_ledger(tmp_path, [row]), now=_NOW) is False

    def test_session_ending_after_now_does_not_count(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        row = _row(key=key_file, ended_at=_NOW + timedelta(minutes=5))
        assert read_today(_ledger(tmp_path, [row]), now=_NOW) is False

    def test_small_session_without_bonus_flag_does_not_count(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        row = _row(key=key_file, bonus="0")
        assert read_today(_ledger(tmp_path, [row]), now=_NOW) is False

    def test_non_credit_rows_never_count(self, tmp_path: Path, key_file: Path) -> None:
        rows = [_row("reject", key=key_file), _row("escape", key=key_file), "junk"]
        assert read_today(_ledger(tmp_path, rows), now=_NOW) is False

    def test_non_dict_detail_does_not_count(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        row = _row(key=key_file, detail="not-a-dict")
        assert read_today(_ledger(tmp_path, [row]), now=_NOW) is False

    def test_forged_credit_is_ignored(self, tmp_path: Path, key_file: Path) -> None:
        row = _row(key=key_file, bonus="0")
        row["detail"]["bonus"] = "1"  # body no longer matches its hmac
        assert read_today(_ledger(tmp_path, [row]), now=_NOW) is False

    @pytest.mark.parametrize("ended_at", ["soon", None])
    def test_unusable_ended_at_does_not_count_and_warns(
        self,
        tmp_path: Path,
        key_file: Path,
        caplog: pytest.LogCaptureFixture,
        ended_at: object,
    ) -> None:
        """A missing ended_at stringifies to "None"; neither may invent a day."""
        row = _row(key=key_file, detail={"bonus": "1", "ended_at": ended_at})
        with caplog.at_level(logging.WARNING):
            assert read_today(_ledger(tmp_path, [row]), now=_NOW) is False
        assert "no usable ended_at" in caplog.text

    def test_one_good_row_among_bad_ones_counts(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        rows = [_row(key=key_file, bonus="0"), _row(key=key_file)]
        assert read_today(_ledger(tmp_path, rows), now=_NOW) is True

    def test_defaults_resolve_module_path_and_clock(
        self, tmp_path: Path, key_file: Path
    ) -> None:
        row = _row(key=key_file, ended_at=datetime.now().astimezone())
        ledger = _ledger(tmp_path, [row])
        with patch.object(_reading_bonus, "READING_LEDGER_FILE", ledger):
            assert read_today() is True


class TestCannotCheck:
    """Every unreadable state is None -- never a confident False."""

    def test_unreadable_key(self, tmp_path: Path) -> None:
        with patch.object(_reading_bonus, "HMAC_KEY_FILE", tmp_path / "no.key"):
            assert read_today(_ledger(tmp_path, [])) is None

    def test_unreadable_key_wins_over_a_missing_ledger(self, tmp_path: Path) -> None:
        """The key is checked first: without it even "no ledger" is unknown."""
        with patch.object(_reading_bonus, "HMAC_KEY_FILE", tmp_path / "no.key"):
            assert read_today(tmp_path / "missing.json") is None

    def test_empty_key(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        key = tmp_path / "hmac.key"
        key.write_bytes(b"  \n")
        with (
            patch.object(_reading_bonus, "HMAC_KEY_FILE", key),
            caplog.at_level(logging.WARNING),
        ):
            assert read_today(_ledger(tmp_path, [])) is None
        assert "is empty" in caplog.text

    def test_invalid_json_is_logged_as_book_guards(
        self, tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "ledger.json"
        path.write_text("{not json")
        with caplog.at_level(logging.WARNING):
            assert read_today(path) is None
        assert "book-guard ledger at" in caplog.text
        assert "not valid JSON" in caplog.text

    def test_no_entries_array(self, tmp_path: Path, key_file: Path) -> None:
        path = tmp_path / "ledger.json"
        path.write_text(json.dumps({"entries": "nope"}))
        assert read_today(path) is None

    def test_unreadable_ledger(self, tmp_path: Path, key_file: Path) -> None:
        """A directory where the file should be: exists, but read_text fails."""
        path = tmp_path / "ledger.json"
        path.mkdir()
        assert read_today(path) is None


class TestBonusHours:
    def test_read_earns_the_hour(self) -> None:
        with patch.object(_reading_bonus, "read_today", return_value=True):
            assert reading_bonus_hours() == READING_BONUS_HOURS == 1

    def test_not_read_earns_nothing(self) -> None:
        with patch.object(_reading_bonus, "read_today", return_value=False):
            assert reading_bonus_hours() == 0

    def test_cannot_check_fails_closed_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch.object(_reading_bonus, "read_today", return_value=None),
            caplog.at_level(logging.WARNING),
        ):
            assert reading_bonus_hours() == 0
        assert "could not be checked" in caplog.text

    def test_passes_the_ledger_path_through(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        with patch.object(_reading_bonus, "read_today", return_value=True) as m:
            reading_bonus_hours(path)
        m.assert_called_once_with(path)

    def test_isolated_suite_never_sees_a_real_ledger(self, key_file: Path) -> None:
        """The conftest redirect points at an absent tmp file, so: 0, not None."""
        assert not _reading_bonus.READING_LEDGER_FILE.exists()
        assert reading_bonus_hours() == 0
