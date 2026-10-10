"""Tests for the reading hour as a term of the shutdown derivation.

Covers the base cut it pays for (20 -> 19 from 2026-10-01), the daily reset
folding the hour in and stamping it, and the live pass that adds it once for a
reading credit landing after the reset. Mirrors test_shutdown_leetcode.py; the
pass over every flat earner is in test_shutdown_flat_earners.py.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import earned_time
import pytest

from screen_locker._day import today_str
from screen_locker._earned import first_credits, gate_earners, hhmm, registry
from screen_locker._shutdown_base import (
    _apply_flat_bonus,
    apply_flat_bonuses_if_new,
    base_minutes,
    reset_to_base_if_new_day,
)
from screen_locker.tests._earned_fixtures import answering

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# Terms the reset log spells out by hand; every later earner follows them.
_NAMED = frozenset({"leetcode", "reading"})


def _mixin(*, adjust_ok: bool = True) -> MagicMock:
    mixin = MagicMock()
    mixin._read_shutdown_config.return_value = (base_minutes(), base_minutes(), 300)
    mixin._write_shutdown_config.return_value = True
    mixin._adjust_shutdown_time_by.return_value = adjust_ok
    return mixin


def apply_reading_bonus_if_new(state: Path, mixin: MagicMock) -> bool:
    """The live pass for the reading earner alone."""
    return _apply_flat_bonus(state, mixin, earned_time.READING)


@pytest.fixture
def answers() -> Iterator[tuple[dict[str, bool | None], MagicMock]]:
    """(answers, earned_today mock): every flat earner says no until set."""
    given: dict[str, bool | None] = {"leetcode": False, "reading": False}
    with answering(given) as mock:
        yield given, mock


class TestBaseHour:
    def test_day_before_the_cut_keeps_twenty(self) -> None:
        assert base_minutes(date(2026, 9, 30)) == 20 * 60

    def test_cut_day_is_nineteen(self) -> None:
        assert earned_time.READING.penalty_from == date(2026, 10, 1)
        assert base_minutes(date(2026, 10, 1)) == 19 * 60

    def test_long_after_the_cut_stays_lowered(self) -> None:
        """No drift back to 20:00: the registry's base for the day holds.

        From earned_time's sleep ladder (2026-10-10) the floor is the ceiling
        minus every earner's first unit, not 20:00 minus the cuts, so the day
        is priced by the registry and only the "stays lowered" part is ours.
        The Anki waiver (``ANKI_WAIVED_FROM``) raises that floor to 19:50, so
        "lowered" means below the uncut 20:00, not at or below 19:00; a gate
        that never paid out (the tutor) spares it (earned_time 0.6.1).
        """
        later = date(2030, 1, 1)
        starts = first_credits(registry(later), later)
        base = earned_time.base_for(later, registry(later), first_credits=starts)
        assert base_minutes(later) == base.shutdown_minutes
        assert base.shutdown_minutes < base_minutes(date(2026, 9, 30))

    def test_default_is_the_local_today(self) -> None:
        assert base_minutes() == base_minutes(datetime.now().astimezone().date())


class TestResetIncludesReading:
    @pytest.mark.usefixtures("pre_ladder")
    def test_reset_writes_base_plus_reading_and_stamps_it(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        answers[0]["reading"] = True
        state = tmp_path / "state.json"
        mixin = _mixin()
        assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_minutes() + 60, base_minutes() + 60, 300, restore=True
        )
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "reading_bonus_date": today_str(),
        }

    @pytest.mark.usefixtures("pre_ladder")
    def test_reset_with_both_flat_hours_stamps_both(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        answers[0]["leetcode"] = True
        answers[0]["reading"] = True
        state = tmp_path / "state.json"
        mixin = _mixin()
        assert reset_to_base_if_new_day(state, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(
            base_minutes() + 120, base_minutes() + 120, 300, restore=True
        )
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "leetcode_bonus_date": today_str(),
            "reading_bonus_date": today_str(),
        }
        apply_flat_bonuses_if_new(state, mixin)
        mixin._adjust_shutdown_time_by.assert_not_called()

    def test_reset_is_still_capped_at_the_ceiling(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        answers[0]["leetcode"] = True
        answers[0]["reading"] = True
        mixin = _mixin()
        with patch("screen_locker._shutdown_target.day_credit_count", return_value=9):
            reset_to_base_if_new_day(
                tmp_path / "state.json", mixin, log_file=tmp_path / "log.json"
            )
        mixin._write_shutdown_config.assert_called_once_with(
            1380, 1380, 300, restore=True
        )

    def test_unknown_reading_earns_nothing_warns_and_is_not_stamped(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The live pass must ask again: a stamp would forfeit the day's hour."""
        answers[0]["reading"] = None
        state = tmp_path / "state.json"
        mixin = _mixin()
        with caplog.at_level("WARNING"):
            assert reset_to_base_if_new_day(state, mixin) is True
        assert "reading state could not be checked" in caplog.text
        base = base_minutes()
        mixin._write_shutdown_config.assert_called_once_with(
            base, base, 300, restore=True
        )
        assert json.loads(state.read_text()) == {"last_reset_date": today_str()}

    @pytest.mark.usefixtures("pre_ladder")
    def test_reset_logs_every_term(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        answers[0]["reading"] = True
        with caplog.at_level("INFO"):
            reset_to_base_if_new_day(tmp_path / "state.json", _mixin())
        base = base_minutes()
        later = "".join(
            f" + 0h {e.label}" for e in gate_earners() if e.name not in _NAMED
        )
        assert (
            f"Daily base reset: {hhmm(base + 60)} (base {hhmm(base)} + 0h workout + "
            f"0h LeetCode + 1h reading{later} already earned today)."
        ) in caplog.text


class TestReadingLivePass:
    @pytest.mark.usefixtures("pre_ladder")
    def test_applies_once_and_stamps(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        answers[0]["reading"] = True
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"last_reset_date": today_str()}))
        mixin = _mixin()
        assert apply_reading_bonus_if_new(state, mixin) is True
        assert apply_reading_bonus_if_new(state, mixin) is False
        mixin._adjust_shutdown_time_by.assert_called_once_with(60)
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "reading_bonus_date": today_str(),
        }

    def test_stamped_today_never_reads_the_ledger(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"reading_bonus_date": today_str()}))
        assert apply_reading_bonus_if_new(state, _mixin()) is False
        answers[1].assert_not_called()

    def test_no_reading_no_write(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        mixin = _mixin()
        assert apply_reading_bonus_if_new(tmp_path / "state.json", mixin) is False
        mixin._adjust_shutdown_time_by.assert_not_called()

    def test_failed_write_leaves_no_stamp_and_warns(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A stamp without a write would silently forfeit the hour for the day."""
        answers[0]["reading"] = True
        state = tmp_path / "state.json"
        mixin = _mixin(adjust_ok=False)
        with caplog.at_level("WARNING"):
            assert apply_reading_bonus_if_new(state, mixin) is False
        assert "reading bonus: failed to write" in caplog.text
        assert not state.exists()

    def test_cannot_check_warns_and_leaves_no_stamp(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unknown is not "no": logged, no hour, and re-asked on the next tick."""
        answers[0]["reading"] = None
        state = tmp_path / "state.json"
        mixin = _mixin()
        with caplog.at_level("WARNING"):
            assert apply_reading_bonus_if_new(state, mixin) is False
        assert "reading state could not be checked" in caplog.text
        mixin._adjust_shutdown_time_by.assert_not_called()
        assert not state.exists()

    @pytest.mark.usefixtures("pre_ladder")
    def test_applied_hour_is_logged(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        answers[0]["reading"] = True
        with caplog.at_level("INFO"):
            assert apply_reading_bonus_if_new(tmp_path / "state.json", _mixin())
        assert "reading bonus: +1h shutdown time today." in caplog.text
