"""Tests for ``_earned.first_credits``: maturity only delays a penalty.

A stand-in earner (``piano``) is registered with a penalty from well before
the pinned day. Its signed ledger lives under the suite's redirected
``LEDGER_HOME``; whether it has ever paid out decides whether its cut applies
(earned_time 0.6.0). Every date is fixed and "today" is pinned on
``_earned.today_str``, so the real calendar cannot move a result.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _earned
from screen_locker._earned import first_credits, registry
from screen_locker._shutdown_base import base_minutes
from screen_locker._shutdown_target import DayInputs, derive, gather
from screen_locker.tests._earned_fixtures import (
    EXTRA,
    credit,
    register,
    signing_key,
    write_ledger,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# Before the sleep ladder (2026-10-10), where a penalty still lowers the
# shutdown base; before the Anki waiver too, so the registry is EARNERS.
_DAY = date(2026, 10, 8)
_ONE = timedelta(days=1)


def _any_credit(row: dict[str, object], window: tuple[float, float]) -> bool:
    """Every verified credit counts: the dating is earned_time's own."""
    del row, window
    return True


# Penalised for days already, never confirmed by kuhy: a new gate.
PIANO = earned_time.Earner(
    name="piano",
    label="Piano",
    gaming_minutes=30,
    shutdown_minutes=30,
    ledger=".local/share/piano_guard/ledger.json",
    match=_any_credit,
    penalty_from=_DAY - 5 * _ONE,
)


@pytest.fixture
def today() -> Iterator[None]:
    """Pin "today" to ``_DAY`` for the history check.

    Yields:
        None, with ``_earned.today_str`` answering ``_DAY``.
    """
    with patch.object(_earned, "today_str", return_value=_DAY.isoformat()):
        yield


@pytest.fixture
def piano(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Register ``piano`` and sign its ledger with a throwaway key.

    Args:
        monkeypatch: Patches the registries.
        tmp_path: Where the key is written.

    Yields:
        None, with ``piano`` in every registry and the key patched.
    """
    register(monkeypatch, PIANO)
    with signing_key(tmp_path):
        yield


def _paid(day: date) -> None:
    """``piano`` paid out once, at noon on ``day``."""
    write_ledger(PIANO, [credit(PIANO, datetime.combine(day, time(12)).astimezone())])


@pytest.mark.usefixtures("today", "piano")
class TestTheMap:
    def test_each_penalised_reader_maps_to_its_first_credit(self) -> None:
        """A bonus, a ledger-less and a matcher-less earner are left out."""
        _paid(_DAY - _ONE)
        never = replace(PIANO, name="never", ledger=".local/share/never/l.json")
        earners = (
            PIANO,
            never,
            EXTRA,
            replace(PIANO, name="bare", ledger=None, match=None),
            replace(PIANO, name="blind", match=None),
        )
        assert first_credits(earners, _DAY) == {"piano": _DAY - _ONE, "never": None}

    def test_a_future_day_is_resolved_too(self) -> None:
        assert first_credits((PIANO,), _DAY + _ONE) == {"piano": None}

    def test_history_is_never_re_resolved(self) -> None:
        assert first_credits((PIANO,), _DAY - _ONE) is None

    def test_an_earned_time_without_maturity_says_so(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delattr(earned_time, "maturity")
        _earned._warn_no_maturity.cache_clear()
        with caplog.at_level(logging.WARNING):
            assert first_credits((PIANO,), _DAY) is None
        _earned._warn_no_maturity.cache_clear()
        assert "no maturity" in caplog.text


class TestTheBase:
    """``base_minutes`` and the derived target agree on who is penalised."""

    @pytest.mark.usefixtures("today")
    def test_only_a_gate_that_paid_out_is_penalised(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Never paid out: free. Paid yesterday: cut. Paid today: from tomorrow."""
        with signing_key(tmp_path):
            without = base_minutes(_DAY)
            register(monkeypatch, PIANO)
            assert base_minutes(_DAY) == without
            assert gather(_DAY, None).resolution.base.shutdown_minutes == without
            _paid(_DAY - _ONE)
            assert base_minutes(_DAY) == without - PIANO.shutdown_minutes
            _paid(_DAY)
            assert base_minutes(_DAY) == without

    @pytest.mark.usefixtures("piano")
    def test_a_past_day_keeps_its_penalty_from_base(self) -> None:
        """History: priced on ``penalty_from`` alone, as it was enforced."""
        later = (_DAY + _ONE).isoformat()
        strict = earned_time.base_for(_DAY, registry(_DAY)).shutdown_minutes
        with patch.object(_earned, "today_str", return_value=later):
            assert base_minutes(_DAY) == strict


@pytest.mark.usefixtures("piano")
class TestDerive:
    def test_first_credits_reach_the_resolution(self) -> None:
        answers = {e.name: False for e in registry(_DAY)}
        lenient = derive(DayInputs(_DAY, answers, first_credits={"piano": None}))
        strict = derive(DayInputs(_DAY, answers))
        assert lenient.resolution.base.shutdown_minutes == (
            strict.resolution.base.shutdown_minutes + PIANO.shutdown_minutes
        )
