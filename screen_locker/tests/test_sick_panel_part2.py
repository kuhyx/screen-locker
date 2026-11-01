"""The lock's reaction to what the embedded sick-day panel reports back."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import sickdays

from screen_locker import _ui_flows_sick
from screen_locker._ui_flows_sick_panel import KEPT_NOTE
from screen_locker.tests._sick_helpers import mark_sick
from screen_locker.tests.test_sick_panel import (
    FakePanel,
    _backdrop,
    _texts,
    locker_fixture,
    panels_fixture,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from screen_locker.screen_lock import ScreenLocker

# Fixtures shared with test_sick_panel: re-exported so pytest finds them here.
__all__ = ["locker_fixture", "panels_fixture"]


class TestSaved:
    """What the lock does for each outcome the panel reports."""

    @pytest.fixture(autouse=True)
    def _no_mark_no_push(self) -> Iterator[tuple[MagicMock, MagicMock]]:
        with (
            patch.object(_ui_flows_sick, "mark_today_sick") as mark,
            patch.object(_ui_flows_sick, "push_in_background") as push,
        ):
            yield mark, push
        # The panel already wrote and started its own sync.
        mark.assert_not_called()
        push.assert_not_called()

    def test_sick_and_standing_down_unlocks_like_the_one_tap(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """A sick day with no workout kept applies the floor, records the decision and unlocks."""
        locker.open_sick_panel()
        day = mark_sick(keep=[sickdays.LOCKER_LEETCODE])
        entry = sickdays.SickDay(
            day=day, is_sick=True, keep=frozenset({sickdays.LOCKER_LEETCODE})
        )
        with patch("screen_locker._startup_checks.record_decision") as record:
            panels[0].on_saved(entry)
        locker._apply_sick_floor.assert_called_once_with()
        assert record.call_args.args[0].reason == "sick_day_marked"
        locker.close.assert_called_once_with()

    def test_sick_but_workout_kept_stays_locked_with_a_note(
        self, mock_tk: MagicMock, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """A sick day that keeps the workout stays locked and shows the kept note."""
        locker.open_sick_panel()
        backdrop = _backdrop(panels[0])
        day = mark_sick(keep=[sickdays.LOCKER_WORKOUT])
        entry = sickdays.SickDay(
            day=day, is_sick=True, keep=frozenset({sickdays.LOCKER_WORKOUT})
        )
        panels[0].on_saved(entry)
        # The 20:00 floor applies on any sick day, keep or not.
        locker._apply_sick_floor.assert_called_once_with()
        locker.close.assert_not_called()
        backdrop.destroy.assert_called_once_with()
        assert KEPT_NOTE in _texts(mock_tk.Label)
        mock_tk.Button.return_value.focus_set.assert_called_once_with()
        back = next(
            c for c in mock_tk.Button.call_args_list if c.kwargs.get("text") == "Back"
        )
        back.kwargs["command"]()
        assert locker._sick_overlay is None

    def test_cleared_closes_the_panel_and_leaves_the_lock(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """Clearing the sick day closes the panel without touching the floor or the lock."""
        locker.open_sick_panel()
        backdrop = _backdrop(panels[0])
        entry = sickdays.SickDay(day=sickdays.today(), is_sick=False)
        panels[0].on_saved(entry)
        backdrop.destroy.assert_called_once_with()
        locker._apply_sick_floor.assert_not_called()
        locker.close.assert_not_called()

    def test_unchanged_save_closes_the_panel_only(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """An unchanged save only closes the panel."""
        locker.open_sick_panel()
        backdrop = _backdrop(panels[0])
        panels[0].on_saved(None)
        backdrop.destroy.assert_called_once_with()
        locker._apply_sick_floor.assert_not_called()
        locker.close.assert_not_called()

    def test_cancel_closes_the_panel_only(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """Cancelling only closes the panel and clears the overlay."""
        locker.open_sick_panel()
        backdrop = _backdrop(panels[0])
        assert panels[0].on_cancel is not None
        panels[0].on_cancel()
        backdrop.destroy.assert_called_once_with()
        assert locker._sick_overlay is None
        locker._apply_sick_floor.assert_not_called()
        locker.close.assert_not_called()
