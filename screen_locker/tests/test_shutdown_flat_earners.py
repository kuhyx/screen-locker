"""Tests for the pass over every flat earner, and for the base it projects.

The registry, not this repo, lists the earners: a newly registered flat
earner must be a term of the reset and an hour of the live pass with no code
here. Also covers one real signed ledger end to end, and the status
projection following the 2026-10-01 reading cut.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import earned_time
import pytest

from screen_locker._day import today_str
from screen_locker._shutdown_base import (
    apply_flat_bonuses_if_new,
    base_hour,
    reset_to_base_if_new_day,
)
from screen_locker._status_data import gather_status
from screen_locker.tests._earned_fixtures import (
    EXTRA,
    answering,
    credit,
    signing_key,
    write_ledger,
)
from screen_locker.tests.test_status_data import _files

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _mixin() -> MagicMock:
    mixin = MagicMock()
    mixin._read_shutdown_config.return_value = (base_hour(), base_hour(), 5)
    mixin._write_shutdown_config.return_value = True
    mixin._adjust_shutdown_time_by.return_value = True
    return mixin


@pytest.fixture
def answers() -> Iterator[dict[str, bool | None]]:
    """Every flat earner says no until a test sets it."""
    given: dict[str, bool | None] = {"leetcode": False, "reading": False}
    with answering(given):
        yield given


@pytest.fixture
def with_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register EXTRA after the existing earners, as a new gate would be."""
    monkeypatch.setattr(earned_time, "EARNERS", (*earned_time.EARNERS, EXTRA))


class TestFlatBonuses:
    def test_both_earned_apply_both_and_keep_both_stamps(
        self, tmp_path: Path, answers: dict[str, bool | None]
    ) -> None:
        """The second save must not overwrite the first one's stamp."""
        answers["leetcode"] = True
        answers["reading"] = True
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
        self, tmp_path: Path, answers: dict[str, bool | None]
    ) -> None:
        answers["reading"] = True
        state = tmp_path / "state.json"
        mixin = _mixin()
        apply_flat_bonuses_if_new(state, mixin)
        mixin._adjust_shutdown_time_by.assert_called_once_with(1)
        assert json.loads(state.read_text()) == {"reading_bonus_date": today_str()}


@pytest.mark.usefixtures("with_extra")
class TestANewlyRegisteredEarner:
    def test_reset_includes_and_stamps_it(
        self, tmp_path: Path, answers: dict[str, bool | None]
    ) -> None:
        answers["extra"] = True
        state = tmp_path / "state.json"
        mixin = _mixin()
        assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_hour() + 1, base_hour() + 1, 5, restore=True
        )
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "extra_bonus_date": today_str(),
        }

    def test_live_pass_applies_it_once(
        self, tmp_path: Path, answers: dict[str, bool | None]
    ) -> None:
        answers["extra"] = True
        state = tmp_path / "state.json"
        mixin = _mixin()
        apply_flat_bonuses_if_new(state, mixin)
        apply_flat_bonuses_if_new(state, mixin)
        mixin._adjust_shutdown_time_by.assert_called_once_with(1)
        assert json.loads(state.read_text()) == {"extra_bonus_date": today_str()}

    def test_its_ledger_is_read_like_any_other(self, tmp_path: Path) -> None:
        write_ledger(EXTRA, [credit(EXTRA)])
        mixin = _mixin()
        with signing_key(tmp_path):
            apply_flat_bonuses_if_new(tmp_path / "state.json", mixin)
        mixin._adjust_shutdown_time_by.assert_called_once_with(1)

    def test_a_penalised_earner_lowers_the_base_from_its_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The base is read from the registry at call time, never a constant."""
        eve, cut = date(2026, 10, 2), date(2026, 10, 3)
        penalised = earned_time.Earner(
            name="cut",
            label="cut",
            gaming_minutes=60,
            shutdown_minutes=60,
            penalty_from=cut,
        )
        before = (base_hour(eve), base_hour(cut))
        monkeypatch.setattr(earned_time, "EARNERS", (*earned_time.EARNERS, penalised))
        assert (base_hour(eve), base_hour(cut)) == (before[0], before[1] - 1)


class TestRealLedgers:
    def test_signed_credits_on_disk_reach_the_reset(self, tmp_path: Path) -> None:
        """No mock between the ledgers and the written hour."""
        write_ledger(earned_time.LEETCODE, [credit(earned_time.LEETCODE)])
        write_ledger(earned_time.READING, [credit(earned_time.READING)])
        state = tmp_path / "state.json"
        mixin = _mixin()
        with signing_key(tmp_path):
            assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_hour() + 2, base_hour() + 2, 5, restore=True
        )
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "leetcode_bonus_date": today_str(),
            "reading_bonus_date": today_str(),
        }


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
