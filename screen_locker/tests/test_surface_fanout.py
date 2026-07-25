"""Per-output fan-out: the point of the gatelock v0.2.0 migration.

Every other test in this suite runs against the single-output default, where
"built on every monitor" and "built on the primary and nowhere else" are
indistinguishable. These run on a two-monitor desk, so a loop that only ever
touched ``surfaces[0]`` fails here and nowhere else.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from screen_locker._surface_group import FrameGroup, TextGroup, WidgetGroup
from screen_locker.tests.conftest import TWO_OUTPUTS, create_locker

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.usefixtures("dual_output")
class TestLockerFansOut:
    """The locker's container group, on two live outputs."""

    def test_one_container_per_output(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The premise the rest of this class rests on."""
        del mock_sys_exit
        locker = create_locker(mock_tk, tmp_path)

        assert len(locker.container.surfaces) == len(TWO_OUTPUTS)

    def test_a_label_is_built_on_every_monitor(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """One ``_label`` call paints both screens, not just the primary."""
        del mock_sys_exit
        locker = create_locker(mock_tk, tmp_path)
        mock_tk.Label.reset_mock()

        locker._label("Great job!")

        assert mock_tk.Label.call_count == len(TWO_OUTPUTS)

    def test_a_button_is_built_on_every_monitor(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Buttons fan out through the row group they are parented to."""
        del mock_sys_exit
        locker = create_locker(mock_tk, tmp_path)
        row = locker._button_row()
        mock_tk.Button.reset_mock()

        locker._button(row, "OK", bg=locker._colors.accent, command=lambda: None)

        assert mock_tk.Button.call_count == len(TWO_OUTPUTS)

    def test_clearing_clears_every_monitor(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A screen change wipes both surfaces, not just the primary."""
        del mock_sys_exit
        locker = create_locker(mock_tk, tmp_path)
        # conftest's tk mock hands out one shared Frame, so identity cannot
        # tell the surfaces apart here -- call counts can. Two surfaces means
        # two sweeps; a loop cropped to the primary would make it one.
        child = MagicMock()
        for frame in locker.container.surfaces:
            frame.winfo_children.reset_mock()
            frame.winfo_children.return_value = [child]

        locker.clear_container()

        surface = locker.container.surfaces[0]
        assert surface.winfo_children.call_count == len(TWO_OUTPUTS)
        assert child.destroy.call_count == len(TWO_OUTPUTS)

    def test_a_dark_output_drops_only_its_own_container(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Teardown is by output name, so the surviving monitor keeps painting."""
        del mock_sys_exit
        locker = create_locker(mock_tk, tmp_path)
        survivor = locker.container.surfaces[1]

        locker.teardown_surface(MagicMock(output_name=TWO_OUTPUTS[0].name))

        assert locker.container.surfaces == [survivor]


class TestGroupsInIsolation:
    """The group primitives, without a locker around them."""

    def test_configure_reaches_a_dead_copy_without_raising(self) -> None:
        """A monitor that vanished mid-update must not break the others."""
        dead, alive = MagicMock(), MagicMock()
        dead.configure.side_effect = tk.TclError("bad window path name")

        WidgetGroup([dead, alive]).configure(text="hi")

        alive.configure.assert_called_once_with(text="hi")

    def test_pack_and_destroy_survive_a_dead_copy(self) -> None:
        """Same tolerance for the other fan-out operations."""
        dead, alive = MagicMock(), MagicMock()
        dead.pack.side_effect = tk.TclError("gone")
        dead.destroy.side_effect = tk.TclError("gone")
        dead.pack_forget.side_effect = tk.TclError("gone")
        group = WidgetGroup([dead, alive])

        group.pack(pady=2)
        group.pack_forget()
        group.destroy()

        alive.pack.assert_called_once_with(pady=2)
        alive.pack_forget.assert_called_once_with()
        alive.destroy.assert_called_once_with()

    def test_clear_survives_a_dead_copy(self) -> None:
        """A frame whose window died is skipped, the live one is emptied."""
        dead, alive = MagicMock(), MagicMock()
        dead.winfo_children.side_effect = tk.TclError("gone")
        child = MagicMock()
        alive.winfo_children.return_value = [child]

        FrameGroup([dead, alive]).clear()

        child.destroy.assert_called_once_with()

    def test_text_reads_whichever_copy_was_typed_into(self) -> None:
        """Text boxes cannot share a variable, so the non-empty one wins."""
        untouched, typed = MagicMock(), MagicMock()
        untouched.get.return_value = "   "
        typed.get.return_value = "I have a migraine"

        group = TextGroup([untouched, typed])

        assert group.get("1.0", "end") == "I have a migraine"

    def test_text_falls_back_to_the_primary_when_all_blank(self) -> None:
        """An untouched form still yields a string for validation to reject."""
        first, second = MagicMock(), MagicMock()
        first.get.return_value = ""
        second.get.return_value = ""

        assert TextGroup([first, second]).get("1.0", "end") == ""

    def test_text_skips_a_dead_copy(self) -> None:
        """A destroyed monitor's box is stepped over, not fatal."""
        dead, typed = MagicMock(), MagicMock()
        dead.get.side_effect = tk.TclError("gone")
        typed.get.return_value = "fever since 3am"

        assert TextGroup([dead, typed]).get("1.0", "end") == "fever since 3am"

    def test_single_builds_a_group_of_one(self) -> None:
        """The non-lock windows' degenerate case."""
        parent = MagicMock()

        group = FrameGroup.single(parent, bg="#000000")

        assert len(group.surfaces) == 1
        group.first.place.assert_called_once()

    def test_discard_is_a_no_op_for_an_unknown_output(self) -> None:
        """Tearing down an output that was never built changes nothing."""
        group = FrameGroup([])
        frame = MagicMock()
        group.add(frame, "DP-0")

        group.discard("HDMI-9")

        assert group.surfaces == [frame]

    def test_child_frame_and_widgets_nest(self) -> None:
        """A group can parent another group, which is what button rows need."""
        group = FrameGroup([MagicMock(), MagicMock()])

        row = group.child_frame(bg="#000000")
        labels = row.child_widgets(lambda _parent, **_kw: MagicMock(), text="hi")

        assert len(row.surfaces) == 2
        assert len(list(labels)) == 2

    def test_winfo_helpers_answer_from_the_primary(self) -> None:
        """Reads that cannot fan out use the primary monitor's copy."""
        first, second = MagicMock(), MagicMock()
        child = MagicMock()
        first.winfo_children.return_value = [child]
        group = FrameGroup([first, second])

        assert group.winfo_children() == [child]
        assert group.winfo_toplevel() is first.winfo_toplevel.return_value
