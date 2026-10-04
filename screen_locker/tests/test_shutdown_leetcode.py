"""Tests for the LeetCode hour as a term of the shutdown derivation.

Two entry points share one stamp: the daily reset folds the hour into its
target and stamps it, and the live pass adds it once for a solve that lands
after the reset. Neither may apply it twice, and neither may lose it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import earned_time
import pytest

from screen_locker._day import today_str
from screen_locker._shutdown_base import (
    _apply_flat_bonus,
    base_hour,
    reset_to_base_if_new_day,
)
from screen_locker.tests._earned_fixtures import answering

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _mixin(*, adjust_ok: bool = True) -> MagicMock:
    mixin = MagicMock()
    mixin._read_shutdown_config.return_value = (base_hour(), base_hour(), 5)
    mixin._write_shutdown_config.return_value = True
    mixin._adjust_shutdown_time_by.return_value = adjust_ok
    return mixin


def apply_leetcode_bonus_if_new(state: Path, mixin: MagicMock) -> bool:
    """The live pass for the LeetCode earner alone."""
    return _apply_flat_bonus(state, mixin, earned_time.LEETCODE)


@pytest.fixture
def solved() -> Iterator[MagicMock]:
    """LeetCode solved today; reading not, so the stamps here are LeetCode's."""
    with answering({"leetcode": True, "reading": False}) as m:
        yield m


@pytest.fixture
def unsolved() -> Iterator[MagicMock]:
    with answering({"leetcode": False, "reading": False}) as m:
        yield m


class TestResetIncludesTheHour:
    def test_reset_writes_base_plus_leetcode(
        self, tmp_path: Path, solved: MagicMock
    ) -> None:
        state = tmp_path / "state.json"
        mixin = _mixin()
        assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_hour() + 1, base_hour() + 1, 5, restore=True
        )
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "leetcode_bonus_date": today_str(),
        }

    def test_reset_without_solve_leaves_no_stamp(
        self, tmp_path: Path, unsolved: MagicMock
    ) -> None:
        state = tmp_path / "state.json"
        assert reset_to_base_if_new_day(state, _mixin()) is True
        assert json.loads(state.read_text()) == {"last_reset_date": today_str()}

    def test_live_pass_after_a_reset_that_included_it_is_a_no_op(
        self, tmp_path: Path, solved: MagicMock
    ) -> None:
        """The 2026-09-13 shape, inverted: reset first, then the tick."""
        state = tmp_path / "state.json"
        mixin = _mixin()
        reset_to_base_if_new_day(state, mixin)
        assert apply_leetcode_bonus_if_new(state, mixin) is False
        mixin._adjust_shutdown_time_by.assert_not_called()


class TestLivePass:
    def test_applies_once_and_stamps(self, tmp_path: Path, solved: MagicMock) -> None:
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"last_reset_date": today_str()}))
        mixin = _mixin()
        assert apply_leetcode_bonus_if_new(state, mixin) is True
        assert apply_leetcode_bonus_if_new(state, mixin) is False
        mixin._adjust_shutdown_time_by.assert_called_once_with(1)
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "leetcode_bonus_date": today_str(),
        }

    def test_yesterdays_stamp_does_not_block_today(
        self, tmp_path: Path, solved: MagicMock
    ) -> None:
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"leetcode_bonus_date": "2000-01-01"}))
        assert apply_leetcode_bonus_if_new(state, _mixin()) is True

    def test_no_solve_no_write(self, tmp_path: Path, unsolved: MagicMock) -> None:
        mixin = _mixin()
        assert apply_leetcode_bonus_if_new(tmp_path / "state.json", mixin) is False
        mixin._adjust_shutdown_time_by.assert_not_called()

    def test_failed_write_leaves_no_stamp(
        self, tmp_path: Path, solved: MagicMock
    ) -> None:
        """A stamp without a write would silently forfeit the hour for the day."""
        state = tmp_path / "state.json"
        assert apply_leetcode_bonus_if_new(state, _mixin(adjust_ok=False)) is False
        assert not state.exists()

    def test_reset_after_a_live_pass_does_not_double(
        self, tmp_path: Path, solved: MagicMock
    ) -> None:
        """Live pass before today's reset: the reset rewrites from scratch."""
        state = tmp_path / "state.json"
        mixin = _mixin()
        assert apply_leetcode_bonus_if_new(state, mixin) is True
        assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_hour() + 1, base_hour() + 1, 5, restore=True
        )
        assert apply_leetcode_bonus_if_new(state, mixin) is False
        mixin._adjust_shutdown_time_by.assert_called_once()

    def test_state_write_failure_is_logged_not_raised(
        self, tmp_path: Path, solved: MagicMock
    ) -> None:
        state = MagicMock()
        state.exists.return_value = False
        state.open.side_effect = OSError("disk full")
        assert apply_leetcode_bonus_if_new(state, _mixin()) is True
