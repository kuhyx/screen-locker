"""Tests for the reading hour as a term of the shutdown derivation.

Covers the base cut it pays for (20 -> 19 from 2026-10-01), the daily reset
folding the hour in and stamping it, and the live pass that adds it once for a
reading credit landing after the reset. Mirrors test_shutdown_leetcode.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker import _shutdown_base
from screen_locker._day import today_str
from screen_locker._shutdown_base import (
    READING_BASE_FROM,
    apply_flat_bonuses_if_new,
    apply_reading_bonus_if_new,
    base_hour,
    reset_to_base_if_new_day,
)
from screen_locker._status_data import gather_status
from screen_locker.tests.test_status_data import _files

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _mixin(*, adjust_ok: bool = True) -> MagicMock:
    mixin = MagicMock()
    mixin._read_shutdown_config.return_value = (base_hour(), base_hour(), 5)
    mixin._write_shutdown_config.return_value = True
    mixin._adjust_shutdown_time_by.return_value = adjust_ok
    return mixin


@pytest.fixture
def hours() -> Iterator[tuple[MagicMock, MagicMock]]:
    """(leetcode, reading) hour sources, both 0 until a test sets them."""
    with (
        patch.object(_shutdown_base, "leetcode_bonus_hours", return_value=0) as lc,
        patch.object(_shutdown_base, "reading_bonus_hours", return_value=0) as rd,
    ):
        yield lc, rd


class TestBaseHour:
    def test_day_before_the_cut_keeps_twenty(self) -> None:
        assert base_hour(date(2026, 9, 30)) == 20

    def test_cut_day_is_nineteen(self) -> None:
        assert date(2026, 10, 1) == READING_BASE_FROM
        assert base_hour(date(2026, 10, 1)) == 19

    def test_long_after_the_cut_stays_nineteen(self) -> None:
        assert base_hour(date(2030, 1, 1)) == 19

    def test_default_is_the_local_today(self) -> None:
        assert base_hour() == base_hour(datetime.now().astimezone().date())


class TestResetIncludesReading:
    def test_reset_writes_base_plus_reading_and_stamps_it(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        hours[1].return_value = 1
        state = tmp_path / "state.json"
        mixin = _mixin()
        assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_hour() + 1, base_hour() + 1, 5, restore=True
        )
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "reading_bonus_date": today_str(),
        }

    def test_reset_with_both_flat_hours_stamps_both(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        hours[0].return_value = 1
        hours[1].return_value = 1
        state = tmp_path / "state.json"
        mixin = _mixin()
        assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_hour() + 2, base_hour() + 2, 5, restore=True
        )
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "leetcode_bonus_date": today_str(),
            "reading_bonus_date": today_str(),
        }
        apply_flat_bonuses_if_new(state, mixin)
        mixin._adjust_shutdown_time_by.assert_not_called()

    def test_reset_is_still_capped_at_the_ceiling(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        hours[0].return_value = 1
        hours[1].return_value = 1
        mixin = _mixin()
        with patch.object(_shutdown_base, "today_earned_bonus_hours", return_value=9):
            reset_to_base_if_new_day(
                tmp_path / "state.json", mixin, log_file=tmp_path / "log.json"
            )
        mixin._write_shutdown_config.assert_called_once_with(23, 23, 5, restore=True)


class TestReadingLivePass:
    def test_applies_once_and_stamps(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        hours[1].return_value = 1
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"last_reset_date": today_str()}))
        mixin = _mixin()
        assert apply_reading_bonus_if_new(state, mixin) is True
        assert apply_reading_bonus_if_new(state, mixin) is False
        mixin._adjust_shutdown_time_by.assert_called_once_with(1)
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "reading_bonus_date": today_str(),
        }

    def test_stamped_today_never_reads_the_ledger(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"reading_bonus_date": today_str()}))
        assert apply_reading_bonus_if_new(state, _mixin()) is False
        hours[1].assert_not_called()

    def test_no_reading_no_write(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        mixin = _mixin()
        assert apply_reading_bonus_if_new(tmp_path / "state.json", mixin) is False
        mixin._adjust_shutdown_time_by.assert_not_called()

    def test_failed_write_leaves_no_stamp_and_warns(
        self,
        tmp_path: Path,
        hours: tuple[MagicMock, MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A stamp without a write would silently forfeit the hour for the day."""
        hours[1].return_value = 1
        state = tmp_path / "state.json"
        mixin = _mixin(adjust_ok=False)
        with caplog.at_level("WARNING"):
            assert apply_reading_bonus_if_new(state, mixin) is False
        assert "Reading bonus: failed to write" in caplog.text
        assert not state.exists()


class TestFlatBonuses:
    def test_both_earned_apply_both_and_keep_both_stamps(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        """The second save must not overwrite the first one's stamp."""
        hours[0].return_value = 1
        hours[1].return_value = 1
        state = tmp_path / "state.json"
        mixin = _mixin()
        apply_flat_bonuses_if_new(state, mixin)
        assert mixin._adjust_shutdown_time_by.call_count == 2
        assert json.loads(state.read_text()) == {
            "leetcode_bonus_date": today_str(),
            "reading_bonus_date": today_str(),
        }
        apply_flat_bonuses_if_new(state, mixin)
        assert mixin._adjust_shutdown_time_by.call_count == 2

    def test_only_reading_earned_applies_only_reading(
        self, tmp_path: Path, hours: tuple[MagicMock, MagicMock]
    ) -> None:
        hours[1].return_value = 1
        state = tmp_path / "state.json"
        mixin = _mixin()
        apply_flat_bonuses_if_new(state, mixin)
        mixin._adjust_shutdown_time_by.assert_called_once_with(1)
        assert json.loads(state.read_text()) == {"reading_bonus_date": today_str()}


class TestProjectionFollowsTheCut:
    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (datetime(2026, 9, 30, 12, 0, tzinfo=UTC), 20),
            (datetime(2026, 10, 2, 12, 0, tzinfo=UTC), 19),
        ],
    )
    def test_rest_of_week_uses_the_base_for_that_day(
        self, tmp_path: Path, now: datetime, expected: int
    ) -> None:
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**_files(tmp_path), now=now)
        assert snap.shutdown.rest_of_week[0].hour == expected
        assert snap.shutdown.next_week_preview[0].hour == expected
