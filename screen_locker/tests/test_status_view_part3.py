"""Tests for status_view.py: Check Phone's week-scan backfill reporting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from screen_locker._status_view_verify import PhoneCheckOutcome
from screen_locker.tests._status_view_helpers import _make_window, _snapshot


class TestPollRoutesPhoneCheckOutcome:
    def test_poll_routes_to_result_when_future_done(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        mock_future = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = PhoneCheckOutcome(
            "phone_verified", "verified", "ok", None
        )
        window._phone_future = mock_future
        with patch.object(window, "_on_phone_check_result") as mock_handle:
            window._poll_phone_check()
        mock_handle.assert_called_once_with(mock_future.result.return_value)


class TestWeekScanBackfillResult:
    def test_week_scan_backfill_shows_fill_message_and_applies_no_credit(
        self, mock_tk: MagicMock
    ) -> None:
        """A week-scan backfill message is shown as-is, no _apply_workout_credit call."""
        fake_verifier = MagicMock()
        window = _make_window(
            mock_tk,
            _snapshot(),
            verifier_factory=lambda _log_file: fake_verifier,
        )
        with patch(
            "screen_locker._status_view_verify.gather_status", return_value=_snapshot()
        ):
            window._on_phone_check_result(
                PhoneCheckOutcome(
                    None,
                    "not_verified",
                    "no lifts",
                    "no run",
                    "Auto-filled 1 workout from earlier this week.",
                )
            )
        assert window._credit_message == "Auto-filled 1 workout from earlier this week."
        assert window._phone_check_result is None
        fake_verifier._apply_workout_credit.assert_not_called()
