"""The live pass and the reset pay a gate's bonus by its signed progress.

``earned_time`` 0.24.0 reads a gate's "done N of M" row; a day with no such
row pays exactly as before, and a credited answer always pays in full. The
live pass records what it applied in ``<name>_bonus_minutes`` so the next
pass pays only the difference (never a claw-back, never twice).

Real signed ledgers under the redirected home; only the shutdown writer is a
mock.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import earned_time
import pytest

from screen_locker._day import today_str
from screen_locker._shutdown_base import (
    apply_flat_bonuses_if_new,
    base_minutes,
)
from screen_locker.tests._earned_fixtures import (
    credit,
    register,
    signing_key,
    write_ledger,
)
from screen_locker.tests._progress_fixtures import (
    ODD,
    paid,
    progress_row,
    put_progress,
)

if TYPE_CHECKING:
    from pathlib import Path

READING = earned_time.READING
_FULL = 60  # reading's rung today


def _mixin() -> MagicMock:
    mixin = MagicMock()
    mixin._read_shutdown_config.return_value = (base_minutes(), base_minutes(), 300)
    mixin._write_shutdown_config.return_value = True
    mixin._adjust_shutdown_time_by.return_value = True
    return mixin


def _state(tmp_path: Path) -> Path:
    """An empty state file path: nothing stamped yet."""
    return tmp_path / "state.json"


def _stamped(state: Path) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(state.read_text())
    return loaded


class TestSeededPasses:
    """The brief's scratch-state evidence, one signed ledger per step."""

    def test_half_then_the_rest_then_nothing(self, tmp_path: Path) -> None:
        """1/2 pays half, a later 2/2 pays only the remainder, a third pays 0."""
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            put_progress(READING, [(1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
            put_progress(READING, [(1, 2), (2, 2)])
            apply_flat_bonuses_if_new(state, mixin)
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [_FULL // 2, _FULL - _FULL // 2]
        assert _stamped(state)["reading_bonus_minutes"] == {
            "date": today_str(),
            "minutes": _FULL,
        }

    def test_no_progress_row_pays_nothing_until_credited(self, tmp_path: Path) -> None:
        """No fact and no credit: still a plain no, nothing stamped."""
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            write_ledger(READING, [])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == []
        assert not state.exists()

    def test_a_credit_pays_full_whatever_the_row_says(self, tmp_path: Path) -> None:
        """A true answer is full pay even beside a 1/4 progress row."""
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            write_ledger(READING, [credit(READING), progress_row(READING, 1, 4)])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [_FULL]

    def test_credit_after_partial_pays_the_remainder(self, tmp_path: Path) -> None:
        """Half paid, then the credit lands: the other half, once."""
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            put_progress(READING, [(1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
            write_ledger(READING, [credit(READING), progress_row(READING, 1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [_FULL // 2, _FULL // 2]

    def test_legacy_date_stamp_pays_nothing_more(self, tmp_path: Path) -> None:
        """A bonus_date of today means the full bonus is in: a mid-day deploy
        never pays twice, even with a complete progress row."""
        state, mixin = _state(tmp_path), _mixin()
        state.write_text(json.dumps({"reading_bonus_date": today_str()}))
        with signing_key(tmp_path):
            write_ledger(READING, [credit(READING), progress_row(READING, 2, 2)])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == []
        assert _stamped(state) == {"reading_bonus_date": today_str()}

    def test_uneven_bonus_rounds_down_and_the_credit_pays_the_exact_rest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """50 min at 1/3 is 16 (floor); the final credit pays 34, not 33."""
        register(monkeypatch, ODD)
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            put_progress(ODD, [(1, 3)])
            apply_flat_bonuses_if_new(state, mixin)
            write_ledger(ODD, [credit(ODD), progress_row(ODD, 1, 3)])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [16, 34]

    def test_a_lost_row_never_claws_back(self, tmp_path: Path) -> None:
        """Progress that vanishes pays less than applied: nothing, stamp kept."""
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            put_progress(READING, [(2, 2)])
            apply_flat_bonuses_if_new(state, mixin)
            put_progress(READING, [(1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [_FULL]
        assert _stamped(state)["reading_bonus_minutes"] == {
            "date": today_str(),
            "minutes": _FULL,
        }

    def test_yesterdays_minutes_stamp_counts_for_nothing(self, tmp_path: Path) -> None:
        """A stamp dated another day is stale: today pays from zero."""
        yesterday = (date.fromisoformat(today_str()) - timedelta(days=1)).isoformat()
        state, mixin = _state(tmp_path), _mixin()
        state.write_text(
            json.dumps({"reading_bonus_minutes": {"date": yesterday, "minutes": 60}})
        )
        with signing_key(tmp_path):
            put_progress(READING, [(1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [_FULL // 2]

    @pytest.mark.parametrize(
        "junk", ["x", {"date": today_str(), "minutes": "7"}, {"date": today_str()}]
    )
    def test_a_malformed_minutes_stamp_counts_as_zero(
        self, tmp_path: Path, junk: object
    ) -> None:
        """A hand-edited stamp earns nothing extra and never raises."""
        state, mixin = _state(tmp_path), _mixin()
        state.write_text(json.dumps({"reading_bonus_minutes": junk}))
        with signing_key(tmp_path):
            put_progress(READING, [(1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [_FULL // 2]

    def test_a_forged_row_pays_nothing(self, tmp_path: Path) -> None:
        """A progress row edited after signing is not a fact."""
        state, mixin = _state(tmp_path), _mixin()
        row = progress_row(READING, 1, 2)
        row["detail"]["done"] = "2"
        with signing_key(tmp_path):
            write_ledger(READING, [row])
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == []

    def test_a_failed_write_stamps_nothing(self, tmp_path: Path) -> None:
        """If the config write fails the next pass pays the whole share."""
        state, mixin = _state(tmp_path), _mixin()
        mixin._adjust_shutdown_time_by.return_value = False
        with signing_key(tmp_path):
            put_progress(READING, [(1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
            mixin._adjust_shutdown_time_by.return_value = True
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == [_FULL // 2, _FULL // 2]

    def test_an_unreadable_ledger_pays_nothing(self, tmp_path: Path) -> None:
        """No ledger file at all is "could not check": nothing, and no stamp."""
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            apply_flat_bonuses_if_new(state, mixin)
        assert paid(mixin) == []
