"""screen_locker._morning_session — the carrot file, read and never re-derived."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    from pathlib import Path

NOW = datetime(2026, 9, 19, 9, 0).astimezone()


def _write(entry: dict[str, object], *, sign: bool = True) -> Path:
    """Write an entry to the redirected file; signed unless told otherwise."""
    if sign:
        entry["hmac"] = compute_entry_hmac(entry)
    path = _morning_session.MORNING_SESSION_FILE
    path.write_text(json.dumps(entry))
    return path


def _entry(
    outcome: str = "completed",
    exempt_until: str | None = "11:00",
    date: str = "2026-09-19",
) -> dict[str, object]:
    entry: dict[str, object] = {"date": date, "outcome": outcome}
    if exempt_until is not None:
        entry["exempt_until"] = (
            datetime.fromisoformat(f"{date}T{exempt_until}").astimezone().isoformat()
        )
    return entry


@pytest.fixture(autouse=True)
def _signing_key(tmp_path: Path) -> None:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key):
        yield


class TestVerdict:
    """One rule: signed, today, not yet expired."""

    def test_completed_grants_until_the_signed_instant(self) -> None:
        _write(_entry())
        skip = morning_skip_today(NOW, wait=False)
        assert skip == MorningSkip("completed", NOW.replace(hour=11))
        assert "no lock until 11:00" in str(skip)

    def test_expired_and_absent_exemptions_grant_nothing(self) -> None:
        _write(_entry())
        assert morning_skip_today(NOW + timedelta(hours=3), wait=False) is None
        _write(_entry("failed", exempt_until=None))
        assert morning_skip_today(NOW, wait=False) is None
        _write({**_entry(), "exempt_until": "later"})
        assert morning_skip_today(NOW, wait=False) is None

    def test_yesterdays_file_is_not_today(self) -> None:
        _write(_entry(date="2026-09-18"))
        assert morning_skip_today(NOW, wait=False) is None

    def test_missing_unreadable_tampered_are_all_nothing(self, tmp_path: Path) -> None:
        assert morning_skip_today(NOW, wait=False) is None
        path = _write(_entry(), sign=False)
        assert morning_skip_today(NOW, wait=False) is None
        path.write_text("[1]")
        assert morning_skip_today(NOW, wait=False) is None
        path.write_text("{")
        assert morning_skip_today(NOW, wait=False) is None
        path.unlink()
        path.mkdir()
        assert morning_skip_today(NOW, wait=False) is None
        assert tmp_path in path.parents

    def test_default_now_is_the_wall_clock(self) -> None:
        _write(
            _entry(
                date=datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d"),
                exempt_until="23:59",
            )
        )
        assert has_workout_skip_today() is True


class TestBootRetry:
    """The enforce path waits for the refresher, bounded; status never does."""

    def test_waits_inside_the_window_then_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        naps: list[float] = []
        # The window is re-checked against the real clock after each nap.
        with (
            patch.object(_morning_session, "MORNING_RETRY_SECONDS", 10.0),
            patch.object(_morning_session, "MORNING_WINDOW", ((0, 0), (23, 59))),
        ):
            assert morning_skip_today(NOW, wait=True, sleep=naps.append) is None
        assert naps == [5.0, 5.0]
        assert "is wake-alarm-session.timer running" in caplog.text

    def test_a_file_landing_mid_wait_is_honoured(self) -> None:
        def land(_seconds: float) -> None:
            _write(
                _entry(
                    date=datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d"),
                    exempt_until="23:59",
                )
            )

        with (
            patch.object(_morning_session, "MORNING_RETRY_SECONDS", 10.0),
            patch.object(_morning_session, "MORNING_WINDOW", ((0, 0), (23, 59))),
        ):
            assert morning_skip_today(NOW, wait=True, sleep=land) is not None

    def test_never_waits_outside_the_window_or_without_wait(self) -> None:
        naps: list[float] = []
        with patch.object(_morning_session, "MORNING_RETRY_SECONDS", 10.0):
            assert (
                morning_skip_today(NOW.replace(hour=14), wait=True, sleep=naps.append)
                is None
            )
            assert morning_skip_today(NOW, wait=False, sleep=naps.append) is None
        assert naps == []
