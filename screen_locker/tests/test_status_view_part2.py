"""Tests for status_view.py: phone-check flow, buttons, main() CLI entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._status_view_verify import PhoneCheckOutcome
from screen_locker._workout_credit import WorkoutCreditResult
from screen_locker.status_view import (
    StatusWindow,
    _compliance_state_word,
    _make_bare_verifier,
    main,
)
from screen_locker.tests._status_view_helpers import (
    _button_texts,
    _lock_explanation,
    _make_window,
    _snapshot,
    _temp_check,
    _texts,
    _week,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


class TestPhoneCheckResultRendering:
    def test_no_result_shows_nothing(self, mock_tk: MagicMock) -> None:
        snap = _snapshot()
        _make_window(mock_tk, snap)
        assert not any("Phone check" in t for t in _texts(mock_tk))

    def test_verified_result_shown_in_green(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._phone_check_result = ("verified", "Workout verified!")
        window.render(_snapshot())
        calls = [
            c
            for c in mock_tk.Label.call_args_list
            if "Phone check" in c.kwargs.get("text", "")
        ]
        assert calls
        assert calls[-1].kwargs.get("fg") == "#00cc44"

    def test_non_verified_result_shown_in_orange(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._phone_check_result = ("no_phone", "Phone not connected")
        window.render(_snapshot())
        calls = [
            c
            for c in mock_tk.Label.call_args_list
            if "Phone check" in c.kwargs.get("text", "")
        ]
        assert calls
        assert calls[-1].kwargs.get("fg") == "#ff8844"


class TestButtons:
    def test_renders_check_phone_refresh_close(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        _make_window(mock_tk, _snapshot(), log_file=temp_log_file)
        assert _button_texts(mock_tk) == {
            "Check Phone",
            "Log Manual Workout",
            "Refresh",
            "Close",
        }


class TestRefreshAndCheckPhoneFlow:
    def test_refresh_clears_phone_result_and_calls_on_refresh(
        self, mock_tk: MagicMock
    ) -> None:
        on_refresh = MagicMock()
        window = _make_window(mock_tk, _snapshot(), on_refresh=on_refresh)
        window._phone_check_result = ("verified", "x")
        window._on_refresh_clicked()
        assert window._phone_check_result is None
        on_refresh.assert_called_once()

    def test_check_phone_submits_future(self, mock_tk: MagicMock) -> None:
        """submit() always returns a Future synchronously.

        Whether the trivial mock call resolves before or after the immediate
        follow-up poll check is a genuine race (background thread vs. this
        thread) — not something to assert either way. The poll-routing logic
        itself is tested deterministically below with hand-built futures.
        """
        fake_verifier = MagicMock()
        fake_verifier._verify_phone_workout = MagicMock(return_value=("verified", "ok"))
        window = _make_window(
            mock_tk, _snapshot(), verifier_factory=lambda _log_file: fake_verifier
        )
        with patch("screen_locker.status_view.gather_status", return_value=_snapshot()):
            window._on_check_phone_clicked()
        assert window._phone_future is not None

    def test_poll_waits_when_future_not_done(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        mock_future = MagicMock()
        mock_future.done.return_value = False
        window._phone_future = mock_future
        with patch.object(window, "_on_phone_check_result") as mock_handle:
            window._poll_phone_check()
        mock_handle.assert_not_called()
        window.root.after.assert_called_with(500, window._poll_phone_check)

    def test_poll_waits_when_future_is_none(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._phone_future = None
        with patch.object(window, "_on_phone_check_result") as mock_handle:
            window._poll_phone_check()
        mock_handle.assert_not_called()

    def test_failed_check_shows_combined_message_and_rerenders(
        self, mock_tk: MagicMock
    ) -> None:
        """Neither source verified → show both messages, apply no credit."""
        window = _make_window(mock_tk, _snapshot())
        with patch(
            "screen_locker._status_view_verify.gather_status", return_value=_snapshot()
        ) as mock_gather:
            window._on_phone_check_result(
                PhoneCheckOutcome(None, "no_phone", "no lifts", "no run")
            )
        assert window._phone_check_result == (
            "no_phone",
            "StrongLifts: no lifts · RunnerUp: no run",
        )
        assert window._credit_message is None
        mock_gather.assert_called_once()

    def test_phone_verified_applies_credit_with_phone_message(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        """A verified StrongLifts result writes and credits using the phone message."""
        fake_verifier = MagicMock()
        fake_verifier._apply_workout_credit = MagicMock(
            return_value=WorkoutCreditResult(
                shutdown_adjusted=True,
                new_debt=None,
                extra_bonus_delta=0,
                weekly_count=1,
                already_counted_today=False,
            )
        )
        window = _make_window(
            mock_tk,
            _snapshot(),
            log_file=temp_log_file,
            verifier_factory=lambda _log_file: fake_verifier,
        )
        with patch(
            "screen_locker._status_view_verify.gather_status", return_value=_snapshot()
        ):
            window._on_phone_check_result(
                PhoneCheckOutcome("phone_verified", "verified", "StrongLifts ok", None)
            )
        assert fake_verifier.workout_data == {
            "type": "phone_verified",
            "source": "StrongLifts ok",
        }
        fake_verifier._apply_workout_credit.assert_called_once()
        assert window._phone_check_result is None
        message = window._credit_message
        assert message is not None
        assert "StrongLifts verified: StrongLifts ok" in message
        assert "Shutdown time +2h later!" in message

    def test_runnerup_verified_credits_using_runnerup_message(
        self, mock_tk: MagicMock, temp_log_file: Path
    ) -> None:
        """A verified RunnerUp fallback credits using the RunnerUp message."""
        fake_verifier = MagicMock()
        fake_verifier._apply_workout_credit = MagicMock(
            return_value=WorkoutCreditResult(
                shutdown_adjusted=False,
                new_debt=None,
                extra_bonus_delta=0,
                weekly_count=1,
                already_counted_today=False,
            )
        )
        window = _make_window(
            mock_tk,
            _snapshot(),
            log_file=temp_log_file,
            verifier_factory=lambda _log_file: fake_verifier,
        )
        with patch(
            "screen_locker._status_view_verify.gather_status", return_value=_snapshot()
        ):
            window._on_phone_check_result(
                PhoneCheckOutcome(
                    "runnerup_verified", "verified", "no lifts", "RunnerUp 5.0 km"
                )
            )
        assert fake_verifier.workout_data == {
            "type": "runnerup_verified",
            "source": "RunnerUp 5.0 km",
        }
        message = window._credit_message
        assert message is not None
        assert "RunnerUp verified: RunnerUp 5.0 km" in message


class TestMakeBareVerifier:
    def test_builds_locker_without_running_init(self, tmp_path: Path) -> None:
        log_file = tmp_path / "workout_log.json"
        verifier = _make_bare_verifier(log_file)
        assert verifier.log_file == log_file
        assert verifier.workout_data == {}


class TestComplianceStateWord:
    def test_lock_when_fired(self) -> None:
        snap = _snapshot(lock_explanation=_lock_explanation(fired=True))
        assert _compliance_state_word(snap) == "lock"

    def test_warn_when_not_fired_but_remaining(self) -> None:
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=False),
            week=_week(remaining=2),
        )
        assert _compliance_state_word(snap) == "warn"

    def test_ok_when_not_fired_and_minimum_met(self) -> None:
        snap = _snapshot(
            lock_explanation=_lock_explanation(fired=False),
            week=_week(remaining=0),
        )
        assert _compliance_state_word(snap) == "ok"


class TestMain:
    def test_summary_flag_prints_and_returns(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("screen_locker.status_view.gather_status", return_value=_snapshot()):
            main(["--summary"])
        out = capsys.readouterr().out
        assert "workouts" in out

    def test_state_flag_prints_and_returns(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch(
            "screen_locker.status_view.gather_status",
            return_value=_snapshot(lock_explanation=_lock_explanation(fired=True)),
        ):
            main(["--state"])
        out = capsys.readouterr().out
        assert out.strip() == "lock"

    def test_no_flags_opens_window(self, mock_tk: MagicMock) -> None:
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
    def test_shows_checking_message_before_result(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = None
        window.render(_snapshot())
        assert any("Checking Warsaw temperature" in t for t in _texts(mock_tk))

    def test_shows_resolved_temperature(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=22.0)
        window.render(_snapshot())
        assert any("Warsaw: 22" in t for t in _texts(mock_tk))

    def test_flags_would_trigger_heat_skip_when_hot(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=35.0)
        window.render(_snapshot())
        assert any("Would trigger heat-skip today." in t for t in _texts(mock_tk))

    def test_does_not_flag_heat_skip_when_below_threshold(
        self, mock_tk: MagicMock
    ) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=22.0)
        window.render(_snapshot())
        assert not any("Would trigger heat-skip today." in t for t in _texts(mock_tk))

    def test_shows_timeout_message(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=None, timed_out=True)
        window.render(_snapshot())
        assert any("timed out" in t for t in _texts(mock_tk))

    def test_shows_failure_message_when_not_timed_out(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        window._temp_result = _temp_check(temp_celsius=None, timed_out=False)
        window.render(_snapshot())
        assert any("failed (network/API error)" in t for t in _texts(mock_tk))


class TestTemperatureCheckFlow:
    def test_init_starts_temperature_future(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        assert window._temp_future is not None

    def test_poll_routes_to_result_when_future_done(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        mock_future = MagicMock()
        mock_future.done.return_value = True
        mock_future.result.return_value = _temp_check(temp_celsius=25.0)
        window._temp_future = mock_future
        with patch.object(window, "_on_temperature_check_result") as mock_handle:
            window._poll_temperature_check()
        mock_handle.assert_called_once_with(mock_future.result.return_value)

    def test_poll_waits_when_future_not_done(self, mock_tk: MagicMock) -> None:
        window = _make_window(mock_tk, _snapshot())
        mock_future = MagicMock()
        mock_future.done.return_value = False
        window._temp_future = mock_future
        with patch.object(window, "_on_temperature_check_result") as mock_handle:
            window._poll_temperature_check()
        mock_handle.assert_not_called()
        window.root.after.assert_called_with(500, window._poll_temperature_check)

    def test_poll_waits_when_future_is_none(self, mock_tk: MagicMock) -> None:
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
        window = _make_window(mock_tk, _snapshot(), on_refresh=MagicMock())
        window._temp_result = _temp_check(temp_celsius=30.0)
        with patch.object(window, "_start_temperature_check") as mock_start:
            window._on_refresh_clicked()
        assert window._temp_result is None
        mock_start.assert_called_once()
