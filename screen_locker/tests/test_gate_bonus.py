"""Tests for counted gate earners (the Automation tutor): paid per unit, live.

A stand-in counted gate (``BLOCKS``) is registered by patching
``earned_time.EARNERS``, the registry seam both the installed earned_time and
the tutor-cutover one (``earners_for``) read, so these hold on either.
"""

from __future__ import annotations

from datetime import date
import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import earned_time
import pytest

from screen_locker._day import today_str
from screen_locker._earned import (
    counted_gate_earners,
    flat_earners,
    gate_answers,
    registry,
    watched_earners,
)
from screen_locker._gate_bonus import applied_units, apply_counted_bonus, reset_stamps
from screen_locker._shutdown_base import (
    apply_flat_bonuses_if_new,
    base_minutes,
    reset_to_base_if_new_day,
)
from screen_locker.tests._earned_fixtures import (
    answering,
    register,
    signed,
    signing_key,
    write_ledger,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _any_credit(row: dict[str, object], window: tuple[float, float]) -> bool:
    del row, window
    return True


# 10 minutes for the first unit, 5 for each further one, on any day: no rung.
BLOCKS = earned_time.Earner(
    name="blocks",
    label="Blocks",
    gaming_minutes=15,
    shutdown_minutes=10,
    kind="counted",
    extra_shutdown_minutes=5,
    ledger=".local/share/blocks_guard/ledger.json",
    match=_any_credit,
)
TODAY = date.fromisoformat(today_str())


def _block(number: int) -> dict[str, Any]:
    return signed(
        {
            "kind": "credit",
            "entry_id": f"s-b{number}",
            "day": today_str(),
            "detail": {"block": number},
        }
    )


def _minutes(units: int) -> int:
    return BLOCKS.shutdown_for(units, TODAY)


@pytest.fixture(autouse=True)
def with_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    register(monkeypatch, BLOCKS)


@pytest.fixture
def key(tmp_path: Path) -> Iterator[Path]:
    with signing_key(tmp_path) as path:
        yield path


@pytest.fixture
def flat_no() -> Iterator[None]:
    with answering({}):
        yield


def _mixin() -> MagicMock:
    mixin = MagicMock()
    mixin._read_shutdown_config.return_value = (base_minutes(), base_minutes(), 300)
    mixin._write_shutdown_config.return_value = True
    mixin._adjust_shutdown_time_by.return_value = True
    return mixin


class TestRegistry:
    def test_counted_gates_are_apart_from_flat_and_the_workout(self) -> None:
        assert counted_gate_earners()[-1] is BLOCKS
        assert earned_time.WORKOUT not in counted_gate_earners()
        assert BLOCKS not in flat_earners()
        assert earned_time.WORKOUT not in watched_earners()
        assert BLOCKS in watched_earners()


@pytest.mark.usefixtures("key", "flat_no")
class TestGateAnswers:
    def test_units_alongside_flat_answers(self) -> None:
        write_ledger(BLOCKS, [_block(1), _block(2)])
        answers = gate_answers()
        assert answers["blocks"] == 2
        assert {e.name for e in flat_earners()} <= set(answers)

    def test_unreadable_ledger_is_none_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = write_ledger(BLOCKS, [])
        path.write_text("{not json", encoding="utf-8")
        assert gate_answers(TODAY)["blocks"] is None
        assert "Blocks state could not be checked" in caplog.text


@pytest.mark.usefixtures("key")
class TestApplyCountedBonus:
    def test_pays_only_the_new_units(self) -> None:
        state: dict[str, Any] = {}
        adjust = MagicMock(return_value=True)
        write_ledger(BLOCKS, [_block(1), _block(2)])
        assert apply_counted_bonus(state, adjust, BLOCKS, today_str())
        write_ledger(BLOCKS, [_block(1), _block(2), _block(3)])
        assert apply_counted_bonus(state, adjust, BLOCKS, today_str())
        assert not apply_counted_bonus(state, adjust, BLOCKS, today_str())
        assert [c.args[0] for c in adjust.call_args_list] == [
            _minutes(2),
            _minutes(3) - _minutes(2),
        ]
        assert state == {"blocks_bonus_units": {"date": today_str(), "units": 3}}

    @pytest.mark.parametrize(
        "stamp",
        [{"date": "2000-01-01", "units": 9}, {"date": None}, "junk", {"units": "x"}],
    )
    def test_a_stale_or_broken_stamp_is_zero(self, stamp: object) -> None:
        assert applied_units({"blocks_bonus_units": stamp}, BLOCKS, today_str()) == 0

    def test_failed_write_keeps_the_stamp(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        state: dict[str, Any] = {}
        write_ledger(BLOCKS, [_block(1)])
        adjust = MagicMock(return_value=False)
        assert not apply_counted_bonus(state, adjust, BLOCKS, today_str())
        assert state == {}
        assert "Blocks bonus: failed to write" in caplog.text

    def test_unknown_earns_nothing_and_says_so(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        write_ledger(BLOCKS, []).write_text("[]", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            assert not apply_counted_bonus({}, MagicMock(), BLOCKS, today_str())
        assert "could not be checked" in caplog.text


@pytest.mark.usefixtures("key", "flat_no")
class TestThroughTheShutdownBase:
    def test_reset_stamps_flat_dates_and_counted_units(self) -> None:
        answers = {"workout": 1, "leetcode": True, "blocks": 2}
        terms = earned_time.resolve(answers, TODAY, registry(TODAY)).terms
        stamps = reset_stamps(terms, today_str())
        assert stamps == {
            "leetcode_bonus_date": today_str(),
            "blocks_bonus_units": {"date": today_str(), "units": 2},
        }

    def test_reset_includes_units_then_live_pass_adds_only_new(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "state.json"
        write_ledger(BLOCKS, [_block(1)])
        mixin = _mixin()
        assert reset_to_base_if_new_day(state, mixin) is True
        written = mixin._write_shutdown_config.call_args.args[0]
        assert written == base_minutes() + _minutes(1)
        saved = json.loads(state.read_text())
        assert saved["blocks_bonus_units"] == {"date": today_str(), "units": 1}
        write_ledger(BLOCKS, [_block(1), _block(2)])
        apply_flat_bonuses_if_new(state, mixin)
        mixin._adjust_shutdown_time_by.assert_called_once_with(
            _minutes(2) - _minutes(1)
        )
        units = json.loads(state.read_text())["blocks_bonus_units"]["units"]
        assert units == 2

    def test_live_pass_without_new_units_writes_nothing(self, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        write_ledger(BLOCKS, [])
        mixin = _mixin()
        apply_flat_bonuses_if_new(state, mixin)
        mixin._adjust_shutdown_time_by.assert_not_called()
        assert not state.exists()
