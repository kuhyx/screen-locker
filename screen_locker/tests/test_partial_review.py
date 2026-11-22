"""The live pass prices the review through ``earned_time.term_for``, not here.

From ``REVIEW_PROGRESS_FROM`` (2026-11-24) a credited review with no verified
progress row pays 0 (the library logs it), a row pays ``20 * done // target``;
before that date the review ignores rows and pays the flat 20. The live pass
holds no pay formula, so each of these is the library's answer.
"""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import earned_time
import pytest

from screen_locker import _shutdown_base
from screen_locker.tests._earned_fixtures import answering, signing_key, write_ledger
from screen_locker.tests._progress_fixtures import paid, progress_row

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

REVIEW = earned_time.REVIEW
_BEFORE = "2026-11-23"
_FROM = earned_time.REVIEW_PROGRESS_FROM.isoformat()


@pytest.fixture(name="credited", autouse=True)
def credited_fixture() -> Iterator[None]:
    """The review gate answers yes (a backed review landed)."""
    with answering({"review": True}):
        yield


def _pass(tmp_path: Path, day: str, rows: list[tuple[int, int]]) -> list[int]:
    """One live pass for the review on ``day``; the minutes pushed."""
    mixin = MagicMock()
    mixin._adjust_shutdown_time_by.return_value = True
    with signing_key(tmp_path), patch.object(_shutdown_base, "today_str", lambda: day):
        write_ledger(REVIEW, [progress_row(REVIEW, d, t, day) for d, t in rows])
        _shutdown_base._apply_flat_bonus(tmp_path / "state.json", mixin, REVIEW)
    return paid(mixin)


def test_the_cutover_is_the_documented_day() -> None:
    """The brief's dates: rows count from 2026-11-24."""
    assert _FROM == "2026-11-24"
    assert date.fromisoformat(_BEFORE) < earned_time.REVIEW_PROGRESS_FROM


def test_credited_with_no_row_pays_nothing_from_the_cutover(tmp_path: Path) -> None:
    """No verified fact, no minutes: never the flat 20 any more."""
    assert _pass(tmp_path, _FROM, []) == []


@pytest.mark.parametrize(("done", "target", "minutes"), [(1, 3, 6), (3, 3, 20)])
def test_a_row_pays_its_share_of_twenty(
    tmp_path: Path, done: int, target: int, minutes: int
) -> None:
    """1/3 is 6, 3/3 is 20, even though the answer is a credited yes."""
    assert _pass(tmp_path, _FROM, [(done, target)]) == [minutes]


@pytest.mark.parametrize("rows", [[], [(1, 3)], [(3, 3)]])
def test_before_the_cutover_a_credit_pays_the_flat_twenty(
    tmp_path: Path, rows: list[tuple[int, int]]
) -> None:
    """Rows are ignored before 2026-11-24: 20 whatever they say."""
    assert _pass(tmp_path, _BEFORE, rows) == [20]


def test_the_rest_is_paid_once_the_row_grows(tmp_path: Path) -> None:
    """6 now, then only the 14 that 3/3 adds, then nothing."""
    mixin = MagicMock()
    mixin._adjust_shutdown_time_by.return_value = True
    state = tmp_path / "state.json"
    with (
        signing_key(tmp_path),
        patch.object(_shutdown_base, "today_str", lambda: _FROM),
    ):
        for rows in ([(1, 3)], [(1, 3), (3, 3)], [(3, 3)]):
            write_ledger(REVIEW, [progress_row(REVIEW, d, t, _FROM) for d, t in rows])
            _shutdown_base._apply_flat_bonus(state, mixin, REVIEW)
    assert paid(mixin) == [6, 14]
    assert json.loads(state.read_text())["review_bonus_minutes"]["minutes"] == 20
