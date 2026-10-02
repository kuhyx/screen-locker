"""screen_locker._morning_session — binds screen-locker's file to gatelock's reader.

The verdict rules themselves (signed, today, not expired, the boot retry) are
tested once, in gatelock.morning_session.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from gatelock.log_integrity import compute_entry_hmac
import pytest

from screen_locker import _morning_session
from screen_locker._morning_session import (
    MorningSkip,
    has_workout_skip_today,
    morning_skip_today,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

NOW = datetime(2026, 9, 19, 9, 0).astimezone()


@pytest.fixture(autouse=True)
def _signing_key(tmp_path: Path) -> Iterator[None]:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key):
        yield


def _write(date: str, exempt_until: str) -> None:
    """Sign an entry into the file the conftest redirected."""
    entry: dict[str, object] = {
        "date": date,
        "outcome": "completed",
        "exempt_until": datetime.fromisoformat(f"{date}T{exempt_until}")
        .astimezone()
        .isoformat(),
    }
    entry["hmac"] = compute_entry_hmac(entry)
    _morning_session.MORNING_SESSION_FILE.write_text(json.dumps(entry))


def test_reads_the_redirected_file() -> None:
    _write("2026-09-19", "11:00")
    skip = morning_skip_today(NOW, wait=False)
    assert skip == MorningSkip("completed", NOW.replace(hour=11))
    assert "no lock until 11:00" in str(skip)


def test_missing_file_is_no_skip() -> None:
    assert morning_skip_today(NOW, wait=False) is None


def test_has_workout_skip_today_uses_the_wall_clock() -> None:
    _write(datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d"), "23:59")
    assert has_workout_skip_today() is True


def test_the_retry_budget_is_screen_lockers_own() -> None:
    """The conftest zeroes it; raising it here makes the shared reader wait."""
    naps: list[float] = []
    assert morning_skip_today(NOW, wait=True, sleep=naps.append) is None
    assert naps == []
    with patch.object(_morning_session, "MORNING_RETRY_SECONDS", 10.0):
        assert morning_skip_today(NOW, wait=True, sleep=naps.append) is None
    assert naps
