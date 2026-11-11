"""The lock's "choose lockers" link: sickdays' KeepPanel, embedded in the lock.

A recording fake replaces the panel. The pool is written for real before
``on_saved`` fires: the lock branches on the pool, not on the entry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import sickdays
import sickdays.gui._panel

from screen_locker import _glyphs as g
from screen_locker import _ui_flows_sick, _ui_flows_sick_panel
from screen_locker._ui_flows_sick_panel import LINK_TEXT, build_sick_panel
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from datetime import date
    from pathlib import Path

    from screen_locker.screen_lock import ScreenLocker


_MADE: list[FakePanel] = []


class FakePanel:
    """Records how the lock built it; ``on_saved``/``on_cancel`` are driven."""

    def __init__(
        self,
        parent: MagicMock,
        day: date,
        *,
        on_saved: Callable[[sickdays.SickDay | None], None],
        on_cancel: Callable[[], None] | None = None,
        paths: sickdays.Paths | None = None,
    ) -> None:
        """Keep every argument for the assertions."""
        self.parent = parent
        self.day = day
        self.on_saved = on_saved
        self.on_cancel = on_cancel
        self.paths = paths
        self.packed = False
        _MADE.append(self)

    def pack(self, **_kwargs: object) -> None:
        """Record that the lock showed it."""
        self.packed = True


def _frame(*args: object, **_kwargs: object) -> MagicMock:
    """A distinct mock frame that remembers its parent, like Tk's ``master``."""
    frame = MagicMock()
    frame.master = args[0] if args else None
    frame.winfo_children.return_value = []
    return frame


@pytest.fixture(name="panels")
def panels_fixture() -> Iterator[list[FakePanel]]:
    """Every KeepPanel the lock builds, in order."""
    _MADE.clear()
    with patch.object(_ui_flows_sick_panel, "KeepPanel", FakePanel):
        yield _MADE


@pytest.fixture(name="locker")
def locker_fixture(
    mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
) -> ScreenLocker:
    """A retry-screen lock whose floor and close are observable."""
    built = create_locker(mock_tk, tmp_path)
    mock_tk.Frame.side_effect = _frame
    object.__setattr__(built, "_apply_sick_floor", MagicMock())
    object.__setattr__(built, "close", MagicMock())
    return built


def _backdrop(panel: FakePanel) -> MagicMock:
    """The full-surface frame the panel's centred box sits on."""
    return panel.parent.master


def _texts(mock: MagicMock) -> list[str]:
    return [str(c.kwargs.get("text", "")) for c in mock.call_args_list]


class TestLink:
    """The "choose lockers" link and how it opens the embedded panel."""

    def test_the_link_sits_next_to_the_one_tap_button(
        self, mock_tk: MagicMock, locker: ScreenLocker
    ) -> None:
        """The link is wired to open_sick_panel and sits right after the sick button."""
        locker._show_retry_and_sick("nope")
        buttons = mock_tk.Button.call_args_list
        texts = _texts(mock_tk.Button)
        sick = next(c for c in buttons if c.kwargs.get("text") == g.SICK)
        link = next(c for c in buttons if c.kwargs.get("text") == LINK_TEXT)
        assert sick.kwargs["command"] == locker.mark_sick_and_unlock
        assert link.kwargs["command"] == locker.open_sick_panel
        assert texts.index(LINK_TEXT) == texts.index(g.SICK) + 1

    def test_opening_builds_todays_panel_on_a_backdrop(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """Opening builds a panel for today, packed and cancellable, on a full-surface backdrop."""
        locker.open_sick_panel()
        panel = panels[0]
        assert panel.day == sickdays.today()
        assert panel.packed
        assert panel.on_cancel is not None
        _backdrop(panel).place.assert_called_once_with(
            relx=0, rely=0, relwidth=1, relheight=1
        )

    @pytest.mark.usefixtures("dual_output")
    def test_every_monitor_gets_a_panel_and_the_primary_gets_focus(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """With two outputs each gets a panel and only the primary takes focus."""
        locker.open_sick_panel()
        assert len(panels) == 2
        panels[0].parent.tk_focusNext.return_value.focus_set.assert_called_once_with()
        panels[1].parent.tk_focusNext.return_value.focus_set.assert_not_called()

    def test_reopening_closes_the_previous_panel(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """Opening the panel again destroys the previous backdrop."""
        locker.open_sick_panel()
        first = _backdrop(panels[0])
        locker.open_sick_panel()
        first.destroy.assert_called_once_with()

    def test_build_sick_panel_passes_paths_through(
        self, mock_tk: MagicMock, panels: list[FakePanel], tmp_path: Path
    ) -> None:
        """build_sick_panel forwards its paths and callbacks to the panel unchanged."""
        paths = sickdays.Paths.under(tmp_path / "pool")
        saved, cancel = MagicMock(), MagicMock()
        build_sick_panel(
            MagicMock(), MagicMock(), on_saved=saved, on_cancel=cancel, paths=paths
        )
        assert panels[0].paths is paths
        assert panels[0].on_saved is saved
        assert panels[0].on_cancel is cancel


class TestOneTapUnchanged:
    """The one-tap sick button keeps its old behaviour next to the panel."""

    def test_one_tap_still_keeps_nothing_and_builds_no_panel(
        self, locker: ScreenLocker, panels: list[FakePanel]
    ) -> None:
        """One tap marks sick with nothing kept, pushes, unlocks and builds no panel."""
        with patch.object(_ui_flows_sick, "push_in_background") as push:
            locker.mark_sick_and_unlock()
        assert sickdays.is_sick_day() is True
        assert sickdays.kept_lockers() == frozenset()
        push.assert_called_once_with()
        locker.close.assert_called_once_with()
        assert panels == []


def test_the_pool_fixture_reaches_the_embedded_panel(tmp_path: Path) -> None:
    """``sickdays.gui._panel`` binds its own ``resolve_paths``/``sync_quietly``."""
    assert sickdays.gui._panel.resolve_paths(None).log == (
        sickdays.Paths.under(tmp_path / "sickdays").log
    )
    assert sickdays.gui._panel.sync_quietly() is False
