"""kuhy's shared credit logo (``kuhy_credit.tk``) on every screen-locker window.

kuhy, 2026-11-21: the logo goes "everywhere in every single app, desktop
program", lockers included. Each lock surface (one per monitor), the
non-lock aux windows, the status window and the heat-skip prompt get one
logo in their bottom-right corner, on the toplevel itself rather than the
repainted content frame, so a flow repaint never wipes it.

``KuhyCredit`` is a real ``tk.Canvas``; the autouse fixture swaps it for a
MagicMock (``screen_locker._credit.KuhyCredit``) like it swaps ``tk``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker import _credit, _heat_skip, status_view
from screen_locker._surface_group import FrameGroup
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


def test_place_credit_puts_the_logo_bottom_right() -> None:
    """The logo sits in the corner, sized from the lock's display type."""
    parent = MagicMock()
    config = MagicMock()
    config.space.return_value = 24
    config.type_px.return_value = 40

    with patch.object(_credit, "KuhyCredit") as credit_cls:
        credit = _credit.place_credit(parent, config)

    credit_cls.assert_called_once_with(parent, theme="dark", size=40)
    config.type_px.assert_called_once_with("display")
    credit.place.assert_called_once_with(relx=1, rely=1, x=-24, y=-24, anchor="se")


@pytest.mark.usefixtures("mock_sys_exit")
class TestLockSurfacesCarryTheCredit:
    """The fullscreen lock: one logo per live output, on the toplevel."""

    def test_each_surface_gets_its_own_logo(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """Each monitor's toplevel carries a logo, not its content frame."""
        locker = create_locker(mock_tk, tmp_path)
        surface = MagicMock()
        surface.output_name = "HDMI-1"
        parent = MagicMock()

        with patch("screen_locker._window_setup.place_credit") as place:
            locker.build_surface(parent, surface)

        place.assert_called_once_with(parent, locker._colors)

    def test_aux_windows_get_a_logo_on_the_root(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """The relaxed-day and verify windows show it on their root."""
        locker = create_locker(mock_tk, tmp_path)
        locker.container = FrameGroup([])

        with patch("screen_locker._window_setup.place_credit") as place:
            locker._ensure_container()

        place.assert_called_once_with(locker.root, locker._colors)


def test_status_window_root_gets_a_logo(mock_tk: MagicMock) -> None:
    """The status window shows the logo on its root."""
    with (
        patch.object(status_view, "gather_status"),
        patch.object(status_view, "StatusWindow"),
        patch.object(status_view, "place_credit") as place,
    ):
        status_view.main([])

    place.assert_called_once_with(
        status_view.tk.Tk.return_value, status_view._STATUS_COLORS
    )


def test_heat_skip_prompt_gets_a_logo(mock_tk: MagicMock) -> None:
    """The fullscreen heat-skip prompt shows the logo too."""

    class _Host(_heat_skip.HeatSkipMixin):
        pass

    mock_tk.Tk.return_value.mainloop.side_effect = None
    with patch.object(_heat_skip, "place_credit") as place:
        _Host()._show_heat_skip_dialog(35.0)

    place.assert_called_once_with(mock_tk.Tk.return_value, _heat_skip._COLORS)
