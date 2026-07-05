"""Tests for wttr.in temperature fetching used by the heat-skip feature."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import urllib.error

from screen_locker._temperature import fetch_current_temp_celsius, is_too_hot


def _mock_urlopen_returning(body: bytes) -> MagicMock:
    mock_response = MagicMock()
    mock_response.read.return_value = body
    mock_urlopen = MagicMock()
    mock_urlopen.return_value.__enter__.return_value = mock_response
    return mock_urlopen


class TestFetchCurrentTempCelsius:
    def test_returns_parsed_temperature_on_success(self) -> None:
        body = b'{"current_condition": [{"temp_C": "27"}]}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            assert fetch_current_temp_celsius("Warsaw") == 27.0

    def test_returns_none_on_url_error(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            side_effect=urllib.error.URLError("unreachable"),
        ):
            assert fetch_current_temp_celsius("Warsaw") is None

    def test_returns_none_on_timeout(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            assert fetch_current_temp_celsius("Warsaw") is None

    def test_returns_none_on_os_error(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            side_effect=OSError("network unreachable"),
        ):
            assert fetch_current_temp_celsius("Warsaw") is None

    def test_returns_none_on_missing_key(self) -> None:
        body = b'{"unexpected": "shape"}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            assert fetch_current_temp_celsius("Warsaw") is None

    def test_returns_none_on_empty_current_condition(self) -> None:
        body = b'{"current_condition": []}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            assert fetch_current_temp_celsius("Warsaw") is None

    def test_returns_none_on_non_numeric_temp(self) -> None:
        body = b'{"current_condition": [{"temp_C": "not-a-number"}]}'
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(body),
        ):
            assert fetch_current_temp_celsius("Warsaw") is None

    def test_returns_none_on_invalid_json(self) -> None:
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            _mock_urlopen_returning(b"not json{{{"),
        ):
            assert fetch_current_temp_celsius("Warsaw") is None


class TestIsTooHot:
    def test_returns_none_when_fetch_fails(self) -> None:
        with patch(
            "screen_locker._temperature.fetch_current_temp_celsius", return_value=None
        ):
            assert is_too_hot("Warsaw", 33) is None

    def test_returns_none_when_below_threshold(self) -> None:
        with patch(
            "screen_locker._temperature.fetch_current_temp_celsius", return_value=20.0
        ):
            assert is_too_hot("Warsaw", 33) is None

    def test_returns_temp_when_at_or_above_threshold(self) -> None:
        with patch(
            "screen_locker._temperature.fetch_current_temp_celsius", return_value=33.0
        ):
            assert is_too_hot("Warsaw", 33) == 33.0
