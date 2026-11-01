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


@pytest.fixture(name="answers")
def answers_fixture() -> Iterator[tuple[dict[str, bool | None], MagicMock]]:
    """(answers, earned_today mock): every flat earner says no until set."""
    given: dict[str, bool | None] = {"leetcode": False, "reading": False}
    with answering(given) as mock:
        yield given, mock


class TestBaseHour:
    """base_minutes lowers the base evening shutdown once the reading cut starts."""

    def test_day_before_the_cut_keeps_twenty(self) -> None:
        """Before the reading cut day the base stays at 20:00."""
        assert base_minutes(date(2026, 9, 30)) == 20 * 60

    def test_cut_day_is_nineteen(self) -> None:
        """On the reading cut day the base is 19:00."""
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
        """Called without a day, base_minutes uses the local today."""
        assert base_minutes() == base_minutes(datetime.now().astimezone().date())


class TestResetIncludesReading:
    """The daily reset folds a paid reading hour in as a term and stamps it."""

    @pytest.mark.usefixtures("pre_ladder")
    def test_reset_writes_base_plus_reading_and_stamps_it(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        """A reading credit raises the reset shutdown by one hour and stamps reading only."""
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
        """Earning both flat hours adds two hours and stamps both, leaving the live pass idle."""
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

    def test_reset_without_the_tutor_stops_an_hour_below_the_ceiling(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        """Nine workouts still pay one rung; the confirmed tutor's 60 is unpaid."""
        answers[0]["leetcode"] = True
        answers[0]["reading"] = True
        mixin = _mixin()
        with patch("screen_locker._shutdown_target.day_credit_count", return_value=9):
            reset_to_base_if_new_day(
                tmp_path / "state.json", mixin, log_file=tmp_path / "log.json"
            )
        mixin._write_shutdown_config.assert_called_once_with(
            1320, 1320, 300, restore=True
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
        """The reset log message spells out every term of the derivation."""
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
