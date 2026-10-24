"""The LeetCode shutdown hour needs the day paid in full (earned_time 0.18.0).

kuhy, 2026-10-24: Saturday cost 5 credits, one problem was solved, and the
+1 h shutdown paid anyway. earned_time now counts only the signed ``leetcode``
charge while the gate is on; screen-locker has to say, live, when the gate is
off (a free day, or a sick day not keeping ``leetcode``), because only then
does one verified solve earn on its own.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import earned_time
import freedays
import pytest
import sickdays

from screen_locker import _earned, _gate_off

SAT = date(2026, 10, 24)


@pytest.fixture
def pools(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Fake the free-day and sick-day pools; flip the returned flags."""
    flags = {"free": False, "sick_off": False}
    monkeypatch.setattr(freedays, "is_free_day", lambda _day=None: flags["free"])

    def stands_down(locker: str, _day: date | None = None) -> bool:
        return locker == sickdays.LOCKER_LEETCODE and flags["sick_off"]

    monkeypatch.setattr(sickdays, "stands_down", stands_down)
    return flags


@pytest.mark.parametrize(
    ("free", "sick_off", "expected"),
    [(False, False, False), (True, False, True), (False, True, True)],
)
def test_gate_off_follows_the_pools(
    pools: dict[str, bool], *, free: bool, sick_off: bool, expected: bool
) -> None:
    pools.update(free=free, sick_off=sick_off)
    assert _gate_off.gate_off(earned_time.LEETCODE, SAT) is expected


def test_only_leetcode_has_a_gate_to_switch_off(pools: dict[str, bool]) -> None:
    pools.update(free=True, sick_off=True)
    assert _gate_off.gate_off(earned_time.READING, SAT) is False


def test_every_ledger_read_passes_it(pools: dict[str, bool]) -> None:
    pools.update(free=True)
    leet = earned_time.LEETCODE
    with (
        patch.object(earned_time, "done_today", return_value=True) as done,
        patch.object(earned_time, "first_credit_at", return_value=1.0) as first,
        patch.object(earned_time, "credit_units", return_value=1) as units,
    ):
        _earned.earned_today(leet)
        _earned.first_credit_time(leet, SAT)
        _earned.earned_units(leet, SAT)
    for mock in (done, first, units):
        assert mock.call_args.kwargs["gate_off"] is True
