"""The daily reset and the derived target pay a gate's bonus by its progress.

``earned_time`` 0.24.0 reads a gate's "done N of M" row; a day with no such
row pays exactly as before, and a credited answer always pays in full. The
live pass records what it applied in ``<name>_bonus_minutes`` so the next
pass pays only the difference (never a claw-back, never twice).

Real signed ledgers under the redirected home; only the shutdown writer is a
mock.
"""

from __future__ import annotations

from datetime import date
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import earned_time
import pytest

from screen_locker import _earned_progress
from screen_locker._day import today_str
from screen_locker._shutdown_base import (
    apply_flat_bonuses_if_new,
    base_minutes,
    reset_to_base_if_new_day,
)
from screen_locker._shutdown_target import DayInputs, derive, gather_inputs
from screen_locker.tests._earned_fixtures import (
    credit,
    signing_key,
    write_ledger,
)
from screen_locker.tests._progress_fixtures import (
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


class TestResetAndTarget:
    """The daily reset and the derived target use the same partial pay."""

    def test_reset_pays_the_share_and_stamps_minutes_not_the_date(
        self, tmp_path: Path
    ) -> None:
        """Stamping bonus_date here would freeze a half for the whole day."""
        state, mixin = _state(tmp_path), _mixin()
        with signing_key(tmp_path):
            put_progress(READING, [(1, 2)])
            assert reset_to_base_if_new_day(state, mixin) is True
            write_ledger(READING, [credit(READING), progress_row(READING, 1, 2)])
            apply_flat_bonuses_if_new(state, mixin)
        base = base_minutes()
        mixin._write_shutdown_config.assert_called_once_with(
            base + _FULL // 2, base + _FULL // 2, 300, restore=True
        )
        assert paid(mixin) == [_FULL // 2]
        assert "reading_bonus_date" not in _stamped(state)

    def test_derive_pays_a_share_for_a_no(self) -> None:
        """A no with progress pays done/target of the rung; a yes pays full."""
        day = date.fromisoformat(today_str())
        flat = {"leetcode": False, "reading": True}
        none = derive(DayInputs(day, flat))
        half = derive(
            DayInputs(day, flat, progress={"leetcode": earned_time.Progress(1, 2)})
        )
        full = derive(
            DayInputs(day, flat, progress={"reading": earned_time.Progress(1, 2)})
        )
        assert half.minutes - none.minutes == _FULL // 2
        assert full.minutes == none.minutes

    def test_gather_reads_signed_progress_but_never_the_workouts(
        self, tmp_path: Path
    ) -> None:
        """The workout is applied by its own mixin: its row never reaches resolve."""
        day = date.fromisoformat(today_str())
        with signing_key(tmp_path):
            put_progress(READING, [(1, 2)])
            write_ledger(earned_time.WORKOUT, [progress_row(earned_time.WORKOUT, 1, 2)])
            inputs = gather_inputs(day, None)
        assert inputs.progress == {"reading": earned_time.Progress(1, 2)}

    def test_no_row_anywhere_passes_no_progress(self, tmp_path: Path) -> None:
        """An empty map is passed as None: resolve is called as before."""
        day = date.fromisoformat(today_str())
        with signing_key(tmp_path):
            assert gather_inputs(day, None).progress is None


class TestWithoutTheReader:
    """An installed earned_time older than 0.24 pays by yes/no, loudly once."""

    def test_progress_map_absent_means_no_progress_and_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No ``progress_map``: ``None``, logged at warning."""
        monkeypatch.delattr(earned_time, "progress_map")
        _earned_progress._warn_no_progress.cache_clear()
        with caplog.at_level(logging.WARNING):
            assert (
                _earned_progress.progress_for(date.fromisoformat(today_str())) is None
            )
        assert "progress" in caplog.text

    @pytest.mark.parametrize("missing", ["term_for", "read_progress"])
    def test_no_term_pricer_pays_the_old_yes_no(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        """Without ``term_for``/``read_progress``: a yes pays the rung, a no 0."""
        monkeypatch.delattr(earned_time, missing)
        day = date.fromisoformat(today_str())
        assert _earned_progress.term_minutes(READING, day, answer=True) == _FULL
        assert not _earned_progress.term_minutes(READING, day, answer=False)
