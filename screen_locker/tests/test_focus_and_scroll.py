"""Keyboard focus and viewport settling on the lock surfaces.

The lock holds a *global* grab with VT switching disabled: a surface where
nothing is focused leaves a keyboard-only user typing into the void, and a
viewport that is never re-settled after a repaint reports the wrong size for
the screen it is showing. Both were shipped without tests in 3e77f4e, and the
scroll behaviour they drive is what moved the screen on its own on
2026-08-03 (see ``gatelock/tests/test_scrollable.py`` for that half).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from screen_locker._surface_group import FrameGroup
from screen_locker._window_setup import _first_focusable
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


def _widget(cls: str, *, takefocus: str = "", children: list | None = None):
    """A widget stand-in that answers only what ``_first_focusable`` asks."""
    widget = MagicMock()
    widget.winfo_class.return_value = cls
    widget.cget.return_value = takefocus
    widget.winfo_children.return_value = children or []
    return widget


class TestFirstFocusable:
    """Which widget the lock hands the keyboard to when a screen appears."""

    def test_picks_the_first_focusable_child(self) -> None:
        """A button after a label is still the first thing focus can land on."""
        label = _widget("Label")
        button = _widget("Button")
        parent = _widget("Frame", children=[label, button])

        assert _first_focusable(parent) is button

    def test_descends_into_containers(self) -> None:
        """Buttons live inside a row frame, not directly on the surface."""
        button = _widget("Button")
        row = _widget("Frame", children=[button])
        parent = _widget("Frame", children=[row])

        assert _first_focusable(parent) is button

    def test_skips_widgets_that_opted_out(self) -> None:
        """``takefocus=0`` means the widget is not in the tab ring at all."""
        opted_out = _widget("Button", takefocus="0")
        real = _widget("Entry")
        parent = _widget("Frame", children=[opted_out, real])

        assert _first_focusable(parent) is real

    def test_returns_none_when_nothing_can_take_focus(self) -> None:
        """A caller must be able to tell "nothing to focus" from "focused"."""
        parent = _widget("Frame", children=[_widget("Label")])

        assert _first_focusable(parent) is None


@pytest.mark.usefixtures("mock_sys_exit")
class TestFocusOnAppear:
    """``on_focus_ready`` is what makes a fresh screen keyboard-operable."""

    def test_focuses_the_first_focusable_widget(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """The hook exists so a button-only screen does not start unfocused."""
        locker = create_locker(mock_tk, tmp_path)
        button = _widget("Button")
        locker.container = FrameGroup([_widget("Frame", children=[button])])

        locker.on_focus_ready(MagicMock())

        button.focus_set.assert_called_once_with()

    def test_no_live_output_is_not_an_error(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """The lock is still held with every monitor dark; nothing to focus."""
        locker = create_locker(mock_tk, tmp_path)

        locker.on_focus_ready(None)  # must not raise

    def test_a_surface_with_nothing_focusable_is_left_alone(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """A pure status screen has no controls, and that is a valid state."""
        locker = create_locker(mock_tk, tmp_path)
        locker.container = FrameGroup([_widget("Frame", children=[_widget("Label")])])

        locker.on_focus_ready(MagicMock())  # must not raise

    def test_no_surfaces_at_all(self, mock_tk: MagicMock, tmp_path: Path) -> None:
        """Focus is requested before any surface exists during startup races."""
        locker = create_locker(mock_tk, tmp_path)
        locker.container = FrameGroup([])

        locker.on_focus_ready(MagicMock())  # must not raise

    def test_focus_first_button_takes_the_primary_surface(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """One screen paints N monitors; the keyboard is at exactly one."""
        locker = create_locker(mock_tk, tmp_path)
        button = _widget("Button")
        row = FrameGroup([_widget("Frame", children=[_widget("Label"), button])])

        locker._focus_first_button(row)

        button.focus_set.assert_called_once_with()

    def test_focus_first_button_without_a_button(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """A row of plain labels must not raise looking for a button."""
        locker = create_locker(mock_tk, tmp_path)
        row = FrameGroup([_widget("Frame", children=[_widget("Label")])])

        locker._focus_first_button(row)  # must not raise


@pytest.mark.usefixtures("mock_sys_exit")
class TestSurfacesSettle:
    """Every repaint has to re-settle the viewport it painted into."""

    def test_settle_finalizes_every_scroller(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """One monitor per scroller, and each one measures its own screen."""
        locker = create_locker(mock_tk, tmp_path)
        first, second = MagicMock(), MagicMock()
        locker._scrollers.clear()
        locker._scrollers.update({"eDP-1": first, "HDMI-1": second})

        locker.settle_surfaces()

        first.finalize.assert_called_once_with()
        second.finalize.assert_called_once_with()

    def test_clearing_the_container_schedules_a_settle(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """The hook that makes settling unforgettable across ~19 repaint sites.

        Scheduled rather than run inline: running it here would measure an
        empty container, since the caller has not painted the new screen yet.
        """
        locker = create_locker(mock_tk, tmp_path)
        locker.root.after_idle.reset_mock()

        locker.clear_container()

        locker.root.after_idle.assert_called_once_with(locker.settle_surfaces)

    def test_a_dark_output_drops_its_scroller(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """A monitor that goes away must not be settled or painted again."""
        locker = create_locker(mock_tk, tmp_path)
        surface = MagicMock()
        surface.output_name = "HDMI-1"
        locker._scrollers["HDMI-1"] = MagicMock()

        locker.teardown_surface(surface)

        assert "HDMI-1" not in locker._scrollers


@pytest.mark.usefixtures("mock_sys_exit")
class TestMultiLineField:
    """``_add_label_text`` is the only Tab-safe multi-line field helper."""

    def test_builds_a_label_and_a_text_box_on_every_monitor(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """Both halves fan out, like every other widget helper here."""
        locker = create_locker(mock_tk, tmp_path)
        parent = locker.container.child_frame(bg=locker._colors.bg)
        mock_tk.Text.reset_mock()

        boxes = locker._add_label_text(parent, label="Why?", height=3)

        assert mock_tk.Text.call_count == len(locker.container.surfaces)
        assert mock_tk.Text.call_args.kwargs["height"] == 3
        assert boxes.first is not None

    def test_the_box_is_not_a_keyboard_dead_end(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """Tk makes <Tab> insert a tab character and refocus the same widget.

        Untreated, that traps a keyboard user inside the field with no
        advertised way out -- on this lock, that means never reaching SUBMIT.
        """
        locker = create_locker(mock_tk, tmp_path)
        parent = locker.container.child_frame(bg=locker._colors.bg)

        boxes = locker._add_label_text(parent, label="Why?")

        bound = [call.args[0] for box in boxes for call in box.bind.call_args_list]
        assert "<Tab>" in bound
        assert "<Shift-Tab>" in bound

    def test_paste_is_disabled(self, mock_tk: MagicMock, tmp_path: Path) -> None:
        """The justification has to be typed, like every other field here."""
        locker = create_locker(mock_tk, tmp_path)
        parent = locker.container.child_frame(bg=locker._colors.bg)

        boxes = locker._add_label_text(parent, label="Why?")

        bound = [call.args[0] for box in boxes for call in box.bind.call_args_list]
        assert "<<Paste>>" in bound
        assert "<Control-v>" in bound
