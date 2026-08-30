"""Tests for wttr.in temperature fetching used by the heat-skip feature."""

from __future__ import annotations

import http.client
import time
from unittest.mock import MagicMock, patch
import urllib.error

from screen_locker._temperature import (
    HARD_TIMEOUT_SECONDS,
    TemperatureCheck,
    fetch_current_temp_with_status,
    submit_background,
)


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


class TestNothingEscapesTheFetch:
    """The heat check must never be able to kill the locker.

    `http.client.HTTPException` inherits Exception, not OSError, so it used to
    escape the fetch, escape `future.result()` (which catches only the
    timeout), and take the process down *before* the "enforced" record was
    written -- a lock that never happened and left no line anywhere.
    """

    def test_an_http_exception_is_a_failed_check_not_a_crash(self) -> None:
        """The specific gap: IncompleteRead is not an OSError."""
        with patch(
            "screen_locker._temperature.urllib.request.urlopen",
            side_effect=http.client.IncompleteRead(b"partial"),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result == TemperatureCheck(temp_celsius=None, timed_out=False)

    def test_a_worker_that_raises_still_resolves_the_future(self) -> None:
        """A future nobody resolves is a hang, not a failure."""
        with patch(
            "screen_locker._temperature._fetch_current_temp_celsius_unbounded",
            side_effect=http.client.BadStatusLine("garbage"),
        ):
            result = fetch_current_temp_with_status("Warsaw")
        assert result.temp_celsius is None
        assert result.timed_out is False

    def test_the_whole_check_is_bounded_by_the_hard_timeout(self) -> None:
        """The user's requirement: at most 5s, then lock regardless."""
        with patch(
            "screen_locker._temperature._fetch_current_temp_celsius_unbounded",
            side_effect=lambda _city: time.sleep(30),
        ):
            started = time.monotonic()
            result = fetch_current_temp_with_status("Warsaw")
            elapsed = time.monotonic() - started
        assert result.timed_out is True
        assert elapsed <= HARD_TIMEOUT_SECONDS + 0.5


class TestSubmitBackground:
    """The daemon thread that replaced ThreadPoolExecutor."""

    def test_it_resolves_with_the_callables_result(self) -> None:
        """The ordinary path every caller depends on."""
        assert submit_background(lambda: 42).result(timeout=5) == 42

    def test_the_thread_is_a_daemon(self) -> None:
        """Non-daemon workers held the process open past sys.exit(0).

        `concurrent.futures` joins its workers in an interpreter-exit hook, so
        a stuck DNS lookup outlived the hard timeout it was supposed to be
        bounded by. A daemon thread is abandoned at exit instead.
        """
        with patch("screen_locker._temperature.threading.Thread") as thread_cls:
            submit_background(lambda: 1)
        assert thread_cls.call_args.kwargs["daemon"] is True
        thread_cls.return_value.start.assert_called_once()
