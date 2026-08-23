"""Tests for the multi-reason annotation on lock decisions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from screen_locker._decision_reasons import collect_reasons, reasons_extra

if TYPE_CHECKING:
    import pytest


class TestCollectReasons:
    """Every condition that holds is reported, not just the first."""

    def test_returns_only_the_predicates_that_hold(self) -> None:
        held = collect_reasons(
            {"a": lambda: True, "b": lambda: False, "c": lambda: True}
        )
        assert held == ["a", "c"]

    def test_empty_when_nothing_holds(self) -> None:
        assert collect_reasons({"a": lambda: False}) == []

    def test_a_failing_predicate_is_reported_and_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A broken annotation must not take down the decision it annotates."""

        def boom() -> bool:
            msg = "log unreadable"
            raise OSError(msg)

        with caplog.at_level(logging.WARNING):
            held = collect_reasons({"a": lambda: True, "boom": boom})

        assert held == ["a"]
        # The omission must be loud: an invisible gap would read as "the
        # condition did not hold", which is the opposite of what happened.
        assert "boom" in caplog.text
        assert "log unreadable" in caplog.text


class TestReasonsExtra:
    """The acting reason is never repeated back as an 'also'."""

    def test_excludes_the_acting_reason(self) -> None:
        extra = reasons_extra(
            "early_bird_window_active",
            {
                "early_bird_window_active": lambda: True,
                "workout_logged_today": lambda: True,
            },
        )
        assert extra == {"also": "workout_logged_today"}

    def test_orders_and_joins_every_other_condition(self) -> None:
        extra = reasons_extra(
            "early_bird_window_active",
            {
                "early_bird_window_active": lambda: True,
                "workout_logged_today": lambda: True,
                "weekly_minimum_met": lambda: True,
            },
        )
        assert extra == {"also": "workout_logged_today,weekly_minimum_met"}

    def test_empty_when_the_acting_reason_is_the_only_one(self) -> None:
        """A single-reason decision keeps rendering exactly its old line."""
        extra = reasons_extra(
            "early_bird_window_active",
            {
                "early_bird_window_active": lambda: True,
                "workout_logged_today": lambda: False,
            },
        )
        assert extra == {}
