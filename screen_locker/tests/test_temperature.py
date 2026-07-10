"""Tests for wttr.in temperature fetching used by the heat-skip feature."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import urllib.error

from screen_locker._temperature import TemperatureCheck, fetch_current_temp_with_status


def _mock_urlopen_returning(body: bytes) -> MagicMock:
    mock_response = MagicMock()
    mock_response.read.return_value = body
    mock_urlopen = MagicMock()
    mock_urlopen.return_value.__enter__.return_value = mock_response
    return mock_urlopen


class TestFetchCurrentTempWithStatus:
    def test_returns_parsed_temperature_on_success(self) -> None:
        body = b'{"current_condition": [{"temp_C": "27"}]}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=27.0, timed_out=False)

    def test_returns_none_on_url_error(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            side_effect=urllib.error.URLError("unreachable"),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_returns_none_on_timeout_error(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_returns_none_on_os_error(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            side_effect=OSError("network unreachable"),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_returns_none_on_missing_key(self) -> None:
        body = b'{"unexpected": "shape"}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_returns_none_on_empty_current_condition(self) -> None:
        body = b'{"current_condition": []}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_returns_none_on_non_numeric_temp(self) -> None:
        body = b'{"current_condition": [{"temp_C": "not-a-number"}]}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_returns_none_on_invalid_json(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(b"not json{{{"),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_reports_timed_out_when_fetch_exceeds_hard_timeout(self) -> None:
        def _slow_fetch(_city: str) -> float | None:
            time.sleep(0.3)
            return 27.0

        with patch(
            "screen_locker._temperature._fetch_current_temp_celsius_unbounded",
            side_effect=_slow_fetch,
        ):
            result = fetch_current_temp_with_status("Warsaw", hard_timeout=0.05)
        assert result == TemperatureCheck(temp_celsius=None, timed_out=True)
