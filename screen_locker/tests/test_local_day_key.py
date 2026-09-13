"""The workout day is the LOCAL calendar day, on every writer and reader.

Regression for 2026-09-13: a manual workout logged at 00:02 local (CEST,
``22:02Z`` the day before) was filed under the previous day because every
day-key derivation used ``datetime.now(tz=UTC)``. The lock check then looked
for the local date, found nothing, and locked the PC — while the trailing
window budget (which does not key on an exact date) happily counted it. Any
log between 00:00 and 02:00 local landed on yesterday.

Each test freezes the clock at that exact instant through
``screen_locker._day`` so the same mismatch can never come back on one of the
fourteen former ``now(tz=UTC)`` sites without failing here.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
import json
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from screen_locker import _day
from screen_locker._compliance_predicates import has_logged_today
from screen_locker._compliance_state import explain_lock_decision
from screen_locker._log_io import load_workout_log
from screen_locker._log_mixin import write_signed_entry
from screen_locker._sick_tracker import SickHistory

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# 00:02:35 on 2026-09-13 in Europe/Warsaw — the football was logged then.
JUST_AFTER_MIDNIGHT_UTC = datetime(2026, 9, 12, 22, 2, 35, tzinfo=UTC)
LOCAL_DAY = "2026-09-13"
UTC_DAY = "2026-09-12"


@pytest.fixture
def warsaw_after_midnight(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin TZ to Europe/Warsaw and the clock to 00:02:35 local on the 13th."""
    monkeypatch.setenv("TZ", "Europe/Warsaw")
    time.tzset()

    class _FrozenClock:
        """Stands in for ``datetime`` inside ``_day``; only ``now`` is called."""

        @staticmethod
        def now(tz: tzinfo | None = None) -> datetime:
            return JUST_AFTER_MIDNIGHT_UTC.astimezone(tz or UTC)

    monkeypatch.setattr(_day, "datetime", _FrozenClock)
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


class TestTodayStr:
    """``_day.today_str`` is the single source of "what day is it"."""

    def test_uses_the_local_calendar_day(self, warsaw_after_midnight: None) -> None:
        assert _day.today_str() == LOCAL_DAY

    def test_explicit_instant_is_converted_to_local(
        self, warsaw_after_midnight: None
    ) -> None:
        assert _day.today_str(JUST_AFTER_MIDNIGHT_UTC) == LOCAL_DAY


class TestAfterMidnightLog:
    """A workout logged just after local midnight counts for the new day."""

    def test_write_and_lock_check_agree(
        self, tmp_path: Path, warsaw_after_midnight: None
    ) -> None:
        log_file = tmp_path / "log.json"
        write_signed_entry(
            log_file,
            _day.today_str(),
            {"type": "manual_workout", "start_time": "14:30"},
        )
        assert list(load_workout_log(log_file)) == [LOCAL_DAY]
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            assert has_logged_today(log_file) is True

    def test_explain_sees_the_workout(
        self, tmp_path: Path, warsaw_after_midnight: None
    ) -> None:
        """The read-only decision chain keys on the same local day."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({LOCAL_DAY: [{"workout_data": {"type": "x"}}]}))
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            result = explain_lock_decision(
                log_file=log_file,
                early_bird_pending_file=tmp_path / "early_bird_pending.json",
                sick_history=SickHistory(),
                extended_early_bird=False,
                weekly_minimum_met=True,
                relaxed_day=False,
                now=JUST_AFTER_MIDNIGHT_UTC,
            )
        assert result.fired is False
        assert result.stage == "already_logged"

    def test_utc_day_entry_does_not_count(
        self, tmp_path: Path, warsaw_after_midnight: None
    ) -> None:
        """An entry filed under the UTC day is yesterday's, not today's."""
        log_file = tmp_path / "log.json"
        log_file.write_text(json.dumps({UTC_DAY: [{"workout_data": {"type": "x"}}]}))
        with patch(
            "screen_locker._compliance_predicates.verify_entry_hmac", return_value=True
        ):
            assert has_logged_today(log_file) is False


class TestCrossDayDedup:
    """``write_signed_entry`` dedups by workout_id across ALL days.

    Moving an entry to its correct day must not let its synced copy re-ingest
    under the old key: the id is globally unique, so the log is searched
    whole, not per day.
    """

    def test_same_workout_id_on_another_day_is_not_appended(
        self, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "log.json"
        data = {"type": "manual_workout", "workout_id": "manual:2026-09-12T14:30"}
        assert write_signed_entry(log_file, LOCAL_DAY, data).appended is True
        result = write_signed_entry(log_file, UTC_DAY, data)
        assert result.appended is False
        assert UTC_DAY not in load_workout_log(log_file)
