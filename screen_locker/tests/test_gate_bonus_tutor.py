"""The real registry's tutor rung through the live pass (earned_time 0.8.0).

Units are credited minutes: a ``detail.minutes`` row pays its minutes, a legacy
block row (no ``detail.minutes``) pays 15, and the rung stops paying at 60.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import earned_time
import pytest

from screen_locker._gate_bonus import apply_counted_bonus
from screen_locker.tests._earned_fixtures import signed, signing_key, write_ledger

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def key(tmp_path: Path) -> Iterator[Path]:
    with signing_key(tmp_path) as path:
        yield path


@pytest.mark.usefixtures("key")
def test_the_real_tutor_rung_pays_legacy_blocks_as_15_minutes_up_to_60() -> None:
    """Legacy block rows (no ``detail.minutes``) pay 15 minutes each (0.8.0)."""
    tutor = getattr(earned_time, "AUTOMATION_TUTOR", None)
    if tutor is None:
        pytest.skip("installed earned_time predates the tutor (< 0.5)")
    cutover = earned_time.TUTOR_FROM.isoformat()
    state: dict[str, Any] = {}
    adjust = MagicMock(return_value=True)
    rows: list[dict[str, Any]] = []
    for number in range(1, 6):
        ended = datetime.combine(earned_time.TUTOR_FROM, time(18, number)).astimezone()
        rows.append(
            signed(
                {
                    "kind": "credit",
                    "entry_id": f"s-b{number}",
                    "day": cutover,
                    "detail": {"block": number, "ended_at": ended.timestamp()},
                }
            )
        )
        write_ledger(tutor, rows)
        apply_counted_bonus(state, adjust, tutor, cutover)
    assert [c.args[0] for c in adjust.call_args_list] == [15, 15, 15, 15]
    # Units are minutes now: five block rows count 75; the cap stops the pay.
    assert state["automation_bonus_units"] == {"date": cutover, "units": 75}


@pytest.mark.usefixtures("key")
def test_the_real_tutor_rung_pays_each_credited_minute() -> None:
    """A per-minute row (``detail.minutes``) pays exactly its minutes."""
    tutor = getattr(earned_time, "AUTOMATION_TUTOR", None)
    if tutor is None:
        pytest.skip("installed earned_time predates the tutor (< 0.5)")
    cutover = earned_time.TUTOR_FROM.isoformat()
    state: dict[str, Any] = {}
    adjust = MagicMock(return_value=True)
    ended = datetime.combine(earned_time.TUTOR_FROM, time(18, 7)).astimezone()
    detail = {"block": 7, "minutes": 7, "ended_at": ended.timestamp()}
    row = {"kind": "credit", "entry_id": "s-m7", "day": cutover, "detail": detail}
    write_ledger(tutor, [signed(row)])
    apply_counted_bonus(state, adjust, tutor, cutover)
    adjust.assert_called_once_with(7)
    assert state["automation_bonus_units"] == {"date": cutover, "units": 7}
