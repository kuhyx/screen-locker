"""Signed progress rows and a state file for the partial-bonus tests.

A progress row is the fact a gate signs, "done N of M for day D"
(``earned_time`` 0.24.0, DOCS-progress.md), written to the gate's own ledger
next to its credits. Like every ledger helper here it signs with
``_earned_fixtures.KEY`` and lands where screen-locker reads it, so the
tests read real signed ledgers, never a mock of the reader.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import earned_time

from screen_locker._day import today_str
from screen_locker.tests._earned_fixtures import _any_credit, signed, write_ledger

if TYPE_CHECKING:
    from unittest.mock import MagicMock

# A flat earner whose rung does not divide by 3 or 2, so a share rounds down.
ODD: Final = earned_time.Earner(
    name="odd",
    label="Odd",
    gaming_minutes=50,
    shutdown_minutes=50,
    ledger=".local/share/odd_guard/ledger.json",
    match=_any_credit,
    progress_source="odd",
)


def progress_row(
    earner: earned_time.Earner,
    done: int,
    target: int,
    day: str | None = None,
) -> dict[str, Any]:
    """A signed progress row for ``earner``'s source (default today)."""
    for_day = day or today_str()
    return signed(
        {
            "kind": "progress",
            "entry_id": f"progress:{for_day}:{done}:{target}",
            "day": for_day,
            "amount": 0,
            "device": "test",
            "created_at": f"{for_day}T12:00:00+00:00",
            "detail": {
                "source": earner.progress_source,
                "for_day": for_day,
                "done": str(done),
                "target": str(target),
            },
        }
    )


def put_progress(earner: earned_time.Earner, rows: list[tuple[int, int]]) -> None:
    """Replace ``earner``'s ledger with one progress row per (done, target)."""
    write_ledger(earner, [progress_row(earner, d, t) for d, t in rows])


def paid(mixin: MagicMock) -> list[int]:
    """The minutes each ``_adjust_shutdown_time_by`` call pushed, in order."""
    return [c.args[0] for c in mixin._adjust_shutdown_time_by.call_args_list]
