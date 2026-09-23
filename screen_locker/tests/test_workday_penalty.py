"""screen_locker._workday_penalty — the stick file, read and never re-derived."""

from __future__ import annotations

from datetime import datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from gatelock.log_integrity import compute_entry_hmac
import pytest

from screen_locker import _workday_penalty
from screen_locker._workday_penalty import workday_penalty_today

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 9, 23, 9, 0).astimezone()


def _write(entry: dict[str, object], *, sign: bool = True) -> Path:
    if sign:
        entry["hmac"] = compute_entry_hmac(entry)
    path = _workday_penalty.WORKDAY_PENALTY_FILE
    path.write_text(json.dumps(entry))
    return path


@pytest.fixture(autouse=True)
def _signing_key(tmp_path: Path) -> None:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key):
        yield


class TestVerdict:
    def test_todays_penalty_applies(self) -> None:
        _write({"penalty_date": "2026-09-23", "issued_date": "2026-09-22"})
        assert workday_penalty_today(NOW) is True

    def test_a_different_dates_penalty_does_not_apply(self) -> None:
        _write({"penalty_date": "2026-09-24", "issued_date": "2026-09-23"})
        assert workday_penalty_today(NOW) is False

    def test_missing_unreadable_tampered_are_all_no_penalty(
        self, tmp_path: Path
    ) -> None:
        assert workday_penalty_today(NOW) is False
        path = _write({"penalty_date": "2026-09-23"}, sign=False)
        assert workday_penalty_today(NOW) is False
        path.write_text("not json")
        assert workday_penalty_today(NOW) is False
        path.write_text("[]")
        assert workday_penalty_today(NOW) is False
        path.unlink()
        assert workday_penalty_today(NOW) is False

    def test_default_now_is_used_when_unset(self) -> None:
        # Not asserting a value -- just that omitting `now` does not raise.
        assert workday_penalty_today() is False
