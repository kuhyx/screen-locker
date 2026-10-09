"""The Automation tutor on a simulated cutover: penalty start and grace floor.

``earned_time.TUTOR_FROM`` is a far-future sentinel, so the cutover is
simulated on a fixed day: the registry's cutover (bound by value in
``_registry`` and ``_ladder``) and the tutor's own ``penalty_from`` move to
:data:`_CUTOVER`. Nothing is written outside the suite's redirected home.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _earned
from screen_locker._earned import first_credits, registry
from screen_locker._grace_floor import first_done_at
from screen_locker._shutdown_target import DayInputs, derive
from screen_locker.tests._earned_fixtures import signed, signing_key, write_ledger

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_CUTOVER = date(2026, 10, 10)


@pytest.fixture
def tutor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
    """The tutor registry from ``_CUTOVER``, its ledger signed, today pinned.

    Args:
        monkeypatch: Moves the cutover.
        tmp_path: Where the key is written.

    Yields:
        The tutor earner, penalised from ``_CUTOVER``.
    """
    item = replace(earned_time.AUTOMATION_TUTOR, penalty_from=_CUTOVER)
    swapped = tuple(
        item if e is earned_time.AUTOMATION_TUTOR else e
        for e in earned_time.TUTOR_EARNERS
    )
    monkeypatch.setattr(earned_time, "TUTOR_EARNERS", swapped)
    monkeypatch.setattr("earned_time._registry.TUTOR_FROM", _CUTOVER)
    monkeypatch.setattr("earned_time._ladder.TUTOR_FROM", _CUTOVER)
    with (
        signing_key(tmp_path),
        patch.object(_earned, "today_str", return_value=_CUTOVER.isoformat()),
    ):
        yield item


def _block(hhmm: str) -> dict[str, Any]:
    hours, minutes = map(int, hhmm.split(":"))
    ended = datetime.combine(_CUTOVER, time(hours, minutes)).astimezone()
    return signed(
        {
            "kind": "credit",
            "entry_id": f"s-b{hhmm}",
            "day": _CUTOVER.isoformat(),
            "detail": {"block": 1, "ended_at": ended.timestamp()},
        }
    )


def test_the_simulated_cutover_registers_the_tutor(tutor: Any) -> None:
    assert tutor in registry(_CUTOVER)
    assert tutor in _earned.gate_earners(_CUTOVER)
    assert tutor not in _earned.flat_earners(_CUTOVER)


@pytest.mark.usefixtures("tutor")
class TestNeverCredited:
    """A tutor that never paid out is not penalised once first_credits is wired."""

    def test_the_map_says_never(self) -> None:
        starts = first_credits(registry(_CUTOVER), _CUTOVER)
        assert starts is not None
        assert starts["automation"] is None

    def test_no_tutor_penalty_on_the_gaming_base(self) -> None:
        answers = {e.name: 0 for e in registry(_CUTOVER)}
        starts = first_credits(registry(_CUTOVER), _CUTOVER)
        wired = derive(DayInputs(_CUTOVER, answers, first_credits=starts))
        unwired = derive(DayInputs(_CUTOVER, answers))
        cut = earned_time.AUTOMATION_TUTOR.max_gaming_minutes
        assert wired.resolution.base.gaming_minutes == (
            unwired.resolution.base.gaming_minutes + cut
        )
        # KNOWN GAP (earned_time 0.6.0): on the sleep ladder the shutdown
        # floor is the ceiling minus every registered earner's full pay and
        # never asks whether a penalty is in force, so a never-credited tutor
        # still costs its shutdown minutes. A fix there flips this assertion.
        assert wired.resolution.base.shutdown_minutes == (
            unwired.resolution.base.shutdown_minutes
        )


@pytest.mark.usefixtures("tutor")
class TestTheGraceFloor:
    """A tutor block is a first task like any other."""

    def test_a_tutor_block_starts_the_floor(self, tutor: Any) -> None:
        write_ledger(tutor, [_block("18:55"), _block("19:10")])
        expected = datetime.combine(_CUTOVER, time(18, 55)).astimezone()
        assert first_done_at(_CUTOVER, None) == expected.timestamp()

    def test_no_block_no_floor(self, tutor: Any) -> None:
        write_ledger(tutor, [])
        assert first_done_at(_CUTOVER, None) is None
