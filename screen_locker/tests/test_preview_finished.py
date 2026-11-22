"""The preview's "done" earner is a finished gate: a yes plus a 1/1 fact.

From 2026-11-24 a credited review with no verified fact pays 0, so the
preview's simulated yes carries the fact a finished gate signs; otherwise its
derived target would not match the live add, which ``term_for`` prices alike.
"""

from __future__ import annotations

from datetime import date

import earned_time

from screen_locker._shutdown_target import DayInputs, derive
from scripts._preview_sim import finished

_DAY = date(2026, 11, 24)


def test_finished_marks_only_the_done_earners() -> None:
    """Each done earner gets 1 of 1; the rest get nothing."""
    assert finished({"review": True, "leetcode": False}) == {
        "review": earned_time.Progress(1, 1)
    }


def test_a_simulated_review_pays_twenty_only_with_the_fact() -> None:
    """With ``finished`` the sim's review adds its 20; the bare yes adds 0."""
    flat = {"review": True}
    none = derive(DayInputs(_DAY, {"review": False})).minutes
    bare = derive(DayInputs(_DAY, flat)).minutes
    fact = derive(DayInputs(_DAY, flat, progress=finished(flat))).minutes
    assert (bare - none, fact - none) == (0, 20)
