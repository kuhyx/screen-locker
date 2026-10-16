"""The one-tap "I'm sick" button and the sickdays seam behind it."""

from __future__ import annotations

from datetime import date, timedelta
import threading
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import freedays
import sickdays

from screen_locker import _sick, _ui_flows_sick
from screen_locker.tests._locker_factories import create_locker_relaxed_day
from screen_locker.tests._sick_helpers import mark_sick
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


def _button_texts(mock_tk: MagicMock) -> list[str]:
    return [str(c.kwargs.get("text", "")) for c in mock_tk.Button.call_args_list]


def _label_texts(mock_tk: MagicMock) -> str:
    return " ".join(str(c.kwargs.get("text", "")) for c in mock_tk.Label.call_args_list)


class TestSeam:
    def test_is_sick_and_sick_dates_read_the_pool(self) -> None:
        assert _sick.is_sick() is False
        day = mark_sick()
        old = mark_sick("2026-06-21")
        assert _sick.is_sick() is True
        assert _sick.is_sick(day - timedelta(days=1)) is False
        assert _sick.sick_dates() >= {day, old}

    def test_mark_today_sick(self) -> None:
        result = _sick.mark_today_sick()
        assert result.ok is True
        assert sickdays.is_sick_day() is True

    def test_already_sick_is_success(self) -> None:
        mark_sick()
        result = _sick.mark_today_sick()
        assert result.ok is True
        assert "already" in result.message

    def test_a_free_day_is_refused_with_the_reason(self) -> None:
        freedays.mark(date.today(), reason="test")
        result = _sick.mark_today_sick()
        assert result.ok is False
        assert result.message
        assert sickdays.is_sick_day() is False

    def test_push_runs_sync_quietly_off_the_ui_thread(self) -> None:
        ran = threading.Event()
        with patch.object(sickdays, "sync_quietly", side_effect=ran.set):
            worker = _sick.push_in_background()
            worker.join(timeout=5)
        assert ran.is_set()
        assert worker.daemon is False


class TestButtonEverywhere:
    def test_retry_screen_always_offers_it(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker._show_retry_and_sick("nope")
        assert "I'm sick" in _button_texts(mock_tk)

    def test_phone_penalty_screen_offers_it_without_waiting(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        locker._show_phone_penalty("no phone")
        assert "I'm sick" in _button_texts(mock_tk)

    def test_relaxed_prompt_and_retry_offer_it(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker_relaxed_day(mock_tk, tmp_path)
        locker._start_relaxed_day_flow()
        assert "I'm sick" in _button_texts(mock_tk)
        mock_tk.Button.reset_mock()
        locker._show_relaxed_retry("nothing", "no_workout")
        assert "I'm sick" in _button_texts(mock_tk)


class TestTap:
    def test_success_marks_lifts_pushes_records_and_unlocks(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        floor, close = MagicMock(), MagicMock()
        object.__setattr__(locker, "_apply_sick_floor", floor)
        object.__setattr__(locker, "close", close)
        with (
            patch.object(_ui_flows_sick, "push_in_background") as push,
            patch("screen_locker._startup_checks.record_decision") as record,
        ):
            locker.mark_sick_and_unlock()
        assert sickdays.is_sick_day() is True
        floor.assert_called_once_with()
        push.assert_called_once_with()
        assert record.call_args.args[0].reason == "sick_day_marked"
        close.assert_called_once_with()

    def test_refusal_stays_locked_and_says_why(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        close = MagicMock()
        object.__setattr__(locker, "close", close)
        refused = _sick.MarkResult(ok=False, message="today is a free day")
        with (
            patch.object(_ui_flows_sick, "mark_today_sick", return_value=refused),
            patch.object(_ui_flows_sick, "push_in_background") as push,
        ):
            locker.mark_sick_and_unlock()
        close.assert_not_called()
        push.assert_not_called()
        assert "today is a free day" in _label_texts(mock_tk)
        back = next(
            c for c in mock_tk.Button.call_args_list if c.kwargs.get("text") == "Back"
        )
        assert back.kwargs["command"] == locker._start_phone_check

    def test_refusal_on_the_relaxed_prompt_goes_back_to_it(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker_relaxed_day(mock_tk, tmp_path)
        locker._show_sick_refused("nope")
        back = next(
            c for c in mock_tk.Button.call_args_list if c.kwargs.get("text") == "Back"
        )
        assert back.kwargs["command"] == locker._start_relaxed_day_flow
