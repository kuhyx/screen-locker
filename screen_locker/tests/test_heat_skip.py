"""Tests for the heat-skip confirmation dialog and log entry."""

from __future__ import annotations

import re
from unittest.mock import MagicMock

from screen_locker._constants import HEAT_SKIP_CITY, HEAT_SKIP_TEMP_THRESHOLD
from screen_locker._heat_skip import HeatSkipMixin


class _HeatSkipHost(HeatSkipMixin):
    """Minimal host exposing just what HeatSkipMixin needs from ScreenLocker."""

    def __init__(self) -> None:
        self.workout_data: dict[str, str] = {}
        self.save_workout_log = MagicMock()


def _button_command(mock_tk: MagicMock, name: str):
    """The command of the button created with Tk widget ``name``.

    By name, not by glyph: the buttons carry symbols only (textgate).
    """
    for call in mock_tk.Button.call_args_list:
        if call.kwargs.get("name") == name:
            return call.kwargs["command"]
    msg = f"No button named {name!r} was created"
    raise AssertionError(msg)


class TestShowHeatSkipDialog:
    """_show_heat_skip_dialog blocks on mainloop() until a button fires destroy()."""

    def test_returns_true_when_skip_clicked(self, mock_tk: MagicMock) -> None:
        """Clicking Skip workout makes the dialog return True and closes the window."""
        host = _HeatSkipHost()

        def _simulate_click() -> None:
            _button_command(mock_tk, "skip")()

        mock_tk.Tk.return_value.mainloop.side_effect = _simulate_click
        assert host._show_heat_skip_dialog(35.0) is True
        mock_tk.Tk.return_value.destroy.assert_called_once()

    def test_returns_false_when_declined(self, mock_tk: MagicMock) -> None:
        """Declining makes the dialog return False."""
        host = _HeatSkipHost()

        def _simulate_click() -> None:
            _button_command(mock_tk, "decline")()

        mock_tk.Tk.return_value.mainloop.side_effect = _simulate_click
        assert host._show_heat_skip_dialog(35.0) is False

    def test_dialog_shows_temperature_and_threshold(self, mock_tk: MagicMock) -> None:
        """The dialog shows the rounded temperature against the threshold, no words."""
        host = _HeatSkipHost()
        mock_tk.Tk.return_value.mainloop.side_effect = None
        host._show_heat_skip_dialog(36.4)
        texts = [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]
        assert any(f"36°C ≥ {HEAT_SKIP_TEMP_THRESHOLD}°C" in t for t in texts)
        # Only the city (config data) may carry letters: no chrome sentence.
        chrome = [t.replace(HEAT_SKIP_CITY, "") for t in texts]
        assert not any(re.search(r"[A-Za-z]{2,}", t) for t in chrome)


class TestSaveHeatSkipLog:
    """_save_heat_skip_log builds workout_data and delegates to save_workout_log."""

    def test_saves_expected_workout_data(self) -> None:
        """A heat skip is saved as a heat_skip entry with the rounded temperature and a city."""
        host = _HeatSkipHost()
        host._save_heat_skip_log(34.6)
        assert host.workout_data["type"] == "heat_skip"
        assert host.workout_data["temperature_celsius"] == "35"
        assert host.workout_data["city"]
        host.save_workout_log.assert_called_once()
