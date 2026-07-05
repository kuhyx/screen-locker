"""Tests for the heat-skip confirmation dialog and log entry."""

from __future__ import annotations

from unittest.mock import MagicMock

from screen_locker._heat_skip import HeatSkipMixin


class _HeatSkipHost(HeatSkipMixin):
    """Minimal host exposing just what HeatSkipMixin needs from ScreenLocker."""

    def __init__(self) -> None:
        self.workout_data: dict[str, str] = {}
        self.save_workout_log = MagicMock()


def _button_command(mock_tk: MagicMock, text: str):
    for call in mock_tk.Button.call_args_list:
        if call.kwargs.get("text") == text:
            return call.kwargs["command"]
    msg = f"No button with text {text!r} was created"
    raise AssertionError(msg)


class TestShowHeatSkipDialog:
    """_show_heat_skip_dialog blocks on mainloop() until a button fires destroy()."""

    def test_returns_true_when_skip_clicked(self, mock_tk: MagicMock) -> None:
        host = _HeatSkipHost()

        def _simulate_click() -> None:
            _button_command(mock_tk, "Skip workout")()

        mock_tk.Tk.return_value.mainloop.side_effect = _simulate_click
        assert host._show_heat_skip_dialog(35.0) is True
        mock_tk.Tk.return_value.destroy.assert_called_once()

    def test_returns_false_when_declined(self, mock_tk: MagicMock) -> None:
        host = _HeatSkipHost()

        def _simulate_click() -> None:
            _button_command(mock_tk, "No, I'll workout")()

        mock_tk.Tk.return_value.mainloop.side_effect = _simulate_click
        assert host._show_heat_skip_dialog(35.0) is False

    def test_dialog_shows_temperature_and_threshold(self, mock_tk: MagicMock) -> None:
        host = _HeatSkipHost()
        mock_tk.Tk.return_value.mainloop.side_effect = None
        host._show_heat_skip_dialog(36.4)
        texts = [c.kwargs.get("text", "") for c in mock_tk.Label.call_args_list]
        assert any("36°C" in t for t in texts)
        assert any("threshold" in t for t in texts)


class TestSaveHeatSkipLog:
    """_save_heat_skip_log builds workout_data and delegates to save_workout_log."""

    def test_saves_expected_workout_data(self) -> None:
        host = _HeatSkipHost()
        host._save_heat_skip_log(34.6)
        assert host.workout_data["type"] == "heat_skip"
        assert host.workout_data["temperature_celsius"] == "35"
        assert host.workout_data["city"]
        host.save_workout_log.assert_called_once()
