"""Tests for the daily reset replaying today's already-earned shutdown credit.

Guards the 2026-09-13 failure: a manual workout logged at 00:02 earned its
hours against the previous day's config, the 09:15 base reset wiped them, and
the bar sat at 21:00 with a counted workout on disk. The reset must now write
``base + what today's log has earned``, counted by the same credit rule as the
weekly total so a synced duplicate of one workout earns once.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from screen_locker._day import today_str
from screen_locker._shutdown_base import (
    base_hour,
    reset_to_base_if_new_day,
    today_earned_bonus_hours,
)
from screen_locker._weekly_check import (
    count_day_credits,
    credit_key,
    day_workout_index,
)
from screen_locker._workout_credit import earned_shutdown_bonus_hours

if TYPE_CHECKING:
    from pathlib import Path

_DAY = "2026-09-13"


def _manual(workout_id: str, *, sync_record_id: str | None = None) -> dict[str, Any]:
    """Build a manual_workout entry, optionally stamped as a synced copy."""
    data: dict[str, Any] = {"type": "manual_workout", "source": "football 11v11"}
    if sync_record_id is not None:
        data["sync_record_id"] = sync_record_id
    return {
        "timestamp": f"{_DAY}T07:40:06+00:00",
        "workout_data": data,
        "workout_id": workout_id,
    }


def _real_2026_09_13() -> list[dict[str, Any]]:
    """The two entries log.json held for 2026-09-13: one football, twice."""
    return [
        _manual("manual:2026-09-12T14:30"),
        _manual("manual:2026-09-13T14:30", sync_record_id="manual:2026-09-12T14:30"),
    ]


def _write_log(log_file: Path, day: str, entries: list[dict[str, Any]]) -> Path:
    log_file.write_text(json.dumps({day: entries}))
    return log_file


class TestEarnedShutdownBonusHours:
    """First credit is worth 2h, every further one 1h."""

    def test_no_credits_earn_nothing(self) -> None:
        assert earned_shutdown_bonus_hours(0) == 0

    def test_negative_is_treated_as_nothing(self) -> None:
        assert earned_shutdown_bonus_hours(-1) == 0

    def test_first_credit_is_two_hours(self) -> None:
        assert earned_shutdown_bonus_hours(1) == 2

    def test_further_credits_add_one_hour_each(self) -> None:
        assert earned_shutdown_bonus_hours(3) == 4


class TestSyncedCopySharesCredit:
    """A sync re-ingesting an entry already on the day is the same workout."""

    def test_real_day_counts_one_credit(self) -> None:
        assert count_day_credits(_DAY, _real_2026_09_13()) == 1

    def test_copy_and_original_share_a_key(self) -> None:
        entries = _real_2026_09_13()
        index = day_workout_index(entries)
        assert credit_key(_DAY, 0, entries[0], index) == credit_key(
            _DAY, 1, entries[1], index
        )

    def test_sync_id_naming_an_absent_entry_stays_separate(self) -> None:
        """A synced manual whose source is NOT on this day is its own workout."""
        entries = [
            _manual("manual:2026-09-13T08:00"),
            _manual(
                "manual:2026-09-13T18:00", sync_record_id="manual:2026-09-13T18:00"
            ),
        ]
        assert count_day_credits(_DAY, entries) == 2

    def test_two_genuine_manual_workouts_still_both_count(self) -> None:
        entries = [
            _manual("manual:2026-09-13T08:00"),
            _manual("manual:2026-09-13T18:00"),
        ]
        assert count_day_credits(_DAY, entries) == 2

    def test_without_sibling_index_keys_by_position(self) -> None:
        copy = _real_2026_09_13()[1]
        assert credit_key(_DAY, 3, copy) == ("manual_workout", f"{_DAY}#3")

    def test_day_workout_index_skips_entries_without_an_id(self) -> None:
        entries = [{"workout_data": {"type": "x"}}, _manual("manual:2026-09-13T08:00")]
        assert day_workout_index(entries) == {"manual:2026-09-13T08:00": 1}

    def test_day_workout_index_keeps_the_first_position_of_a_repeated_id(self) -> None:
        entries = [
            _manual("manual:2026-09-13T08:00"),
            _manual("manual:2026-09-13T08:00"),
        ]
        assert day_workout_index(entries) == {"manual:2026-09-13T08:00": 0}

    def test_non_string_sync_id_is_ignored(self) -> None:
        entry = _manual("manual:2026-09-13T08:00")
        entry["workout_data"]["sync_record_id"] = 42
        assert credit_key(_DAY, 0, entry, {"42": 5}) == ("manual_workout", f"{_DAY}#0")


class TestTodayEarnedBonusHours:
    """The log → hours derivation the reset relies on."""

    def test_real_day_earns_two_hours(self, tmp_path: Path) -> None:
        log = _write_log(tmp_path / "log.json", _DAY, _real_2026_09_13())
        assert today_earned_bonus_hours(log, _DAY) == 2

    def test_day_absent_from_log_earns_nothing(self, tmp_path: Path) -> None:
        log = _write_log(tmp_path / "log.json", "2026-09-12", _real_2026_09_13())
        assert today_earned_bonus_hours(log, _DAY) == 0

    def test_non_dict_entries_are_ignored(self, tmp_path: Path) -> None:
        log = tmp_path / "log.json"
        log.write_text(
            json.dumps({_DAY: ["garbage", _manual("manual:2026-09-13T08:00")]})
        )
        assert today_earned_bonus_hours(log, _DAY) == 2


class TestResetReplaysTodaysCredit:
    """reset_to_base_if_new_day writes base + earned, capped at the ceiling."""

    def _mixin(self) -> MagicMock:
        mixin = MagicMock()
        mixin._read_shutdown_config.return_value = (20, 20, 5)
        mixin._write_shutdown_config.return_value = True
        return mixin

    def _state(self, tmp_path: Path) -> Path:
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"last_reset_date": "2000-01-01"}))
        return state

    def test_writes_base_plus_todays_earned_hours(self, tmp_path: Path) -> None:
        """The 2026-09-13 case: base + one football (2h), not the bare base."""
        log = _write_log(tmp_path / "log.json", today_str(), _real_2026_09_13())
        mixin = self._mixin()
        assert (
            reset_to_base_if_new_day(self._state(tmp_path), mixin, log_file=log) is True
        )
        mixin._write_shutdown_config.assert_called_once_with(
            base_hour() + 2, base_hour() + 2, 5, restore=True
        )

    def test_without_log_file_writes_plain_base(self, tmp_path: Path) -> None:
        mixin = self._mixin()
        assert reset_to_base_if_new_day(self._state(tmp_path), mixin) is True
        base = base_hour()
        mixin._write_shutdown_config.assert_called_once_with(
            base, base, 5, restore=True
        )

    def test_empty_day_writes_plain_base(self, tmp_path: Path) -> None:
        log = _write_log(tmp_path / "log.json", "2000-01-01", _real_2026_09_13())
        mixin = self._mixin()
        assert (
            reset_to_base_if_new_day(self._state(tmp_path), mixin, log_file=log) is True
        )
        base = base_hour()
        mixin._write_shutdown_config.assert_called_once_with(
            base, base, 5, restore=True
        )

    def test_earned_hours_are_capped_at_the_restore_ceiling(
        self, tmp_path: Path
    ) -> None:
        """base + 2h football + 3 extra workouts > 23 under either base; clamped."""
        entries = [
            *_real_2026_09_13(),
            _manual("manual:2026-09-13T12:00"),
            _manual("manual:2026-09-13T18:00"),
            _manual("manual:2026-09-13T20:00"),
        ]
        log = _write_log(tmp_path / "log.json", today_str(), entries)
        mixin = self._mixin()
        assert reset_to_base_if_new_day(self._state(tmp_path), mixin, log_file=log)
        mixin._write_shutdown_config.assert_called_once_with(23, 23, 5, restore=True)

    def test_state_file_records_only_the_date(self, tmp_path: Path) -> None:
        """Tomorrow's reset must start from the constant, not from today's total."""
        log = _write_log(tmp_path / "log.json", today_str(), _real_2026_09_13())
        state = self._state(tmp_path)
        reset_to_base_if_new_day(state, self._mixin(), log_file=log)
        assert json.loads(state.read_text()) == {"last_reset_date": today_str()}
