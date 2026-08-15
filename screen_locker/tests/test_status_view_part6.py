"""Tests for status_view.py: phone-check flow, buttons, main() CLI entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.status_view import (
    StatusWindow,
    main,
)
from screen_locker.tests._status_view_helpers import (
    _lock_explanation,
    _make_window,
    _snapshot,
    _temp_check,
    _texts,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


class TestMain:
    """Main."""

    def test_summary_flag_prints_and_returns(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Summary flag prints and returns."""
        with patch("screen_locker.status_view.gather_status", return_value=_snapshot()):
            main(["--summary"])
        out = capsys.readouterr().out
        assert "workouts" in out

    def test_state_flag_prints_and_returns(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """State flag prints and returns."""
        with patch(
            "screen_locker.status_view.gather_status",
            return_value=_snapshot(lock_explanation=_lock_explanation(fired=True)),
        ):
            main(["--state"])
        out = capsys.readouterr().out
        assert out.strip() == "lock"

    def test_no_flags_opens_window(self, mock_tk: MagicMock) -> None:
        """No flags opens window."""
        with patch("screen_locker.status_view.gather_status", return_value=_snapshot()):
            main([])
        mock_tk.Tk.assert_called_once()
        mock_tk.Tk.return_value.mainloop.assert_called_once()

    def test_no_flags_refresh_closure_regathers_and_rerenders(
        self, mock_tk: MagicMock
    ) -> None:
        """Exercises main()'s inner refresh() closure passed as on_refresh."""
        captured: dict[str, Callable[[], None]] = {}

        class _CapturingWindow(StatusWindow):
            def __init__(
                self,
                root: object,
                snapshot: object,
                *,
                on_refresh: Callable[[], None],
                **kwargs: object,
            ) -> None:
                captured["on_refresh"] = on_refresh
                super().__init__(root, snapshot, on_refresh=on_refresh, **kwargs)

        with (
            patch(
                "screen_locker.status_view.gather_status", return_value=_snapshot()
            ) as mock_gather,
            patch("screen_locker.status_view.StatusWindow", _CapturingWindow),
        ):
            main([])
            calls_before = mock_gather.call_count
            captured["on_refresh"]()

        assert mock_gather.call_count == calls_before + 1


class TestTemperatureSectionRendering:
    """TemperatureSectionRendering."""

    def test_shows_checking_message_before_result(self, mock_tk: MagicMock) -> None:
        """Shows checking message before result."""
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = None
        window.render(_snapshot())
        assert any("Checking Warsaw temperature" in t for t in _texts(mock_tk))

    def test_shows_resolved_temperature(self, mock_tk: MagicMock) -> None:
        """Shows resolved temperature."""
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=22.0)
        window.render(_snapshot())
        assert any("Warsaw: 22" in t for t in _texts(mock_tk))

    def test_flags_would_trigger_heat_skip_when_hot(self, mock_tk: MagicMock) -> None:
        """Flags would trigger heat skip when hot."""
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=35.0)
        window.render(_snapshot())
        assert any("Would trigger heat-skip today." in t for t in _texts(mock_tk))

    def test_does_not_flag_heat_skip_when_below_threshold(
        self, mock_tk: MagicMock
    ) -> None:
        """Does not flag heat skip when below threshold."""
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=22.0)
        window.render(_snapshot())
        assert not any("Would trigger heat-skip today." in t for t in _texts(mock_tk))

    def test_shows_timeout_message(self, mock_tk: MagicMock) -> None:
        """Shows timeout message."""
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=None, timed_out=True)
        window.render(_snapshot())
        assert any("timed out" in t for t in _texts(mock_tk))

    def test_shows_failure_message_when_not_timed_out(self, mock_tk: MagicMock) -> None:
        """Shows failure message when not timed out."""
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=None, timed_out=False)
        window.render(_snapshot())
        assert any("failed (network/API error)" in t for t in _texts(mock_tk))


class TestTemperatureCheckFlow:
    """TemperatureCheckFlow."""

    def test_init_starts_temperature_future(self, mock_tk: MagicMock) -> None:
        """Init starts temperature future."""
        window = _make_window(mock_tk, _snapshot())
        assert window._temp_future is not None

    def test_poll_routes_to_result_when_future_done(self, mock_tk: MagicMock) -> None:
        """Poll routes to result when future done."""
        window = _make_window(mock_tk, _snapshot())
        mock_future = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = _temp_check(temp_celsius=25.0)
        window._temp_future = mock_future
        with patch.object(window, "_on_temperature_check_result") as mock_handle:
            window._poll_temperature_check()
        mock_handle.assert_called_once_with(mock_future.result.return_value)

    def test_poll_waits_when_future_not_done(self, mock_tk: MagicMock) -> None:
        """Poll waits when future not done."""
        window = _make_window(mock_tk, _snapshot())
        mock_future = MagicMock()
        mock_future.done.return_value = False
        window._temp_future = mock_future
        with patch.object(window, "_on_temperature_check_result") as mock_handle:
            window._poll_temperature_check()
        mock_handle.assert_not_called()
        window.root.after.assert_called_with(500, window._poll_temperature_check)

    def test_poll_waits_when_future_is_none(self, mock_tk: MagicMock) -> None:
        """Poll waits when future is none."""
        window = _make_window(mock_tk, _snapshot())
        window._temp_future = None
        with patch.object(window, "_on_temperature_check_result") as mock_handle:
            window._poll_temperature_check()
        mock_handle.assert_not_called()

    def test_result_rerenders_last_snapshot_without_gathering_from_disk(
        self, mock_tk: MagicMock
    ) -> None:
        """The temperature reading is independent of on-disk workout state —
        must not trigger a real ``gather_status()`` disk read."""
        window = _make_window(mock_tk, _snapshot())
        result = _temp_check(temp_celsius=19.0)
        with patch("screen_locker.status_view.gather_status") as mock_gather:
            window._on_temperature_check_result(result)
        assert window._temp_result == result
        mock_gather.assert_not_called()

    def test_refresh_clears_result_and_restarts_check(self, mock_tk: MagicMock) -> None:
        """Refresh clears result and restarts check."""
        window = _make_window(mock_tk, _snapshot(), on_refresh=MagicMock())
        window._temp_result = _temp_check(temp_celsius=30.0)
        with patch.object(window, "_start_temperature_check") as mock_start:
            window._on_refresh_clicked()
        assert window._temp_result is None
        mock_start.assert_called_once()
