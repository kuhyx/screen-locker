"""The one-tap "I'm sick" button and the sickdays seam behind it."""

from __future__ import annotations

from datetime import date, timedelta
import threading
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import freedays
import sickdays

from screen_locker import _sick, _ui_flows_sick
from screen_locker._auto_upgrade import AutoUpgradeMixin
from screen_locker._compliance_predicates import is_sick_day_today
from screen_locker.tests._locker_factories import create_locker_relaxed_day
from screen_locker.tests._sick_helpers import mark_sick
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


def _button_texts(mock_tk: MagicMock) -> list[str]:
    """Return the text of every Button created on the mocked tk module."""
    return [str(c.kwargs.get("text", "")) for c in mock_tk.Button.call_args_list]


def _label_texts(mock_tk: MagicMock) -> str:
    """Return the text of every Label created on the mocked tk module, joined."""
    return " ".join(str(c.kwargs.get("text", "")) for c in mock_tk.Label.call_args_list)


class TestSeam:
    """The _sick seam over the sickdays pool: queries, keep sets and the tap."""

    def test_is_sick_and_sick_dates_read_the_pool(self) -> None:
        """is_sick and sick_dates reflect exactly the days marked in the pool."""
        assert _sick.is_sick() is False
        day = mark_sick()
        old = mark_sick("2026-06-21")
        assert _sick.is_sick() is True
        assert _sick.is_sick(day - timedelta(days=1)) is False
        assert _sick.sick_dates() >= {day, old}

    def test_stands_down_workout_follows_the_keep_set(self) -> None:
        """The workout stands down only on sick days that do not keep the workout locker."""
        day = mark_sick(keep=[sickdays.LOCKER_WORKOUT])
        other = mark_sick(day + timedelta(days=1), keep=[sickdays.LOCKER_LEETCODE])
        assert _sick.stands_down_workout(day) is False
        assert _sick.stands_down_workout(other) is True
        assert _sick.stands_down_workout(other + timedelta(days=1)) is False
        # The shutdown floor ignores keep: the day is sick either way.
        assert _sick.is_sick(day) is True

    def test_stands_down_workout_defaults_to_today(self) -> None:
        """Without a date, stands_down_workout asks about today."""
        assert _sick.stands_down_workout() is False
        mark_sick()
        assert _sick.stands_down_workout() is True

    def test_workout_standdown_dates_drop_the_kept_days(self) -> None:
        """Stand-down dates exclude days that keep the workout, unlike sick_dates."""
        kept = mark_sick("2026-06-21", keep=[sickdays.LOCKER_WORKOUT])
        off = mark_sick("2026-07-24")
        assert _sick.workout_standdown_dates() >= {off}
        assert kept not in _sick.workout_standdown_dates()
        assert _sick.sick_dates() >= {kept, off}

    def test_the_startup_ladder_asks_the_workout_switch(self) -> None:
        """``_is_sick_day_today`` is what the lock skip reads: keep-aware."""
        mark_sick(keep=[sickdays.LOCKER_WORKOUT])
        assert AutoUpgradeMixin._is_sick_day_today(MagicMock()) is False
        sickdays.set_kept_lockers(sickdays.today(), [sickdays.LOCKER_BOOK])
        assert AutoUpgradeMixin._is_sick_day_today(MagicMock()) is True

    def test_the_pool_fixture_covers_keep_edits(self) -> None:
        """``set_kept_lockers`` must land in the tmp pool, never the real one."""
        day = mark_sick()
        sickdays.set_kept_lockers(day, [sickdays.LOCKER_DIET])
        assert sickdays.kept_lockers(day) == {sickdays.LOCKER_DIET}

    def test_the_status_predicate_follows_the_workout_switch(self) -> None:
        """The status-window sick predicate follows the workout keep switch."""
        mark_sick(keep=[sickdays.LOCKER_WORKOUT])
        assert is_sick_day_today() is False
        sickdays.set_kept_lockers(sickdays.today(), [sickdays.LOCKER_LEETCODE])
        assert is_sick_day_today() is True

    def test_mark_today_sick(self) -> None:
        """mark_today_sick succeeds and today becomes a sick day."""
        result = _sick.mark_today_sick()
        assert result.ok is True
        assert sickdays.is_sick_day() is True

    def test_the_one_tap_button_keeps_nothing(self) -> None:
        """The lock screen's "I'm sick" is ALL-OFF: every locker stands down."""
        assert _sick.mark_today_sick().ok is True
        assert sickdays.kept_lockers() == frozenset()
        for locker in sickdays.LOCKERS:
            assert sickdays.stands_down(locker) is True
        assert _sick.stands_down_workout() is True

    def test_already_sick_is_success(self) -> None:
        """Marking an already sick day succeeds and says it was already marked."""
        mark_sick()
        result = _sick.mark_today_sick()
        assert result.ok is True
        assert "already" in result.message

    def test_one_tap_on_a_day_that_keeps_lockers_clears_the_keep_set(self) -> None:
        """One tap is ALL-OFF even on a sick day that already keeps lockers."""
        mark_sick(keep=(sickdays.LOCKER_WORKOUT, sickdays.LOCKER_LEETCODE))
        result = _sick.mark_today_sick()
        assert result.ok is True
        assert sickdays.kept_lockers() == frozenset()
        assert _sick.stands_down_workout() is True

    def test_one_tap_that_cannot_clear_the_keep_set_stays_locked(self) -> None:
        """If the keep set cannot be cleared the tap fails with the pool error message."""
        mark_sick(keep=(sickdays.LOCKER_WORKOUT,))
        with patch.object(
            sickdays,
            "set_kept_lockers",
            side_effect=sickdays.UnreadablePoolError("pool unreadable"),
        ):
            result = _sick.mark_today_sick()
        assert result.ok is False
        assert "pool unreadable" in result.message

    def test_a_free_day_is_refused_with_the_reason(self) -> None:
        """A free day refuses the sick mark with a message and stays not sick."""
        freedays.mark(date.today(), reason="test")
        result = _sick.mark_today_sick()
        assert result.ok is False
        assert result.message
        assert sickdays.is_sick_day() is False

    def test_push_runs_sync_quietly_off_the_ui_thread(self) -> None:
        """The background push runs sync_quietly on a separate non-daemon thread."""
        ran = threading.Event()
        with patch.object(sickdays, "sync_quietly", side_effect=ran.set):
            worker = _sick.push_in_background()
            worker.join(timeout=5)
        assert ran.is_set()
        assert worker.daemon is False


class TestButtonEverywhere:
    """Every lock screen that can dead-end offers the I'm sick button."""

    def test_retry_screen_always_offers_it(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The retry screen shows the I'm sick button."""
        locker = create_locker(mock_tk, tmp_path)
        locker._show_retry_and_sick("nope")
        assert "I'm sick" in _button_texts(mock_tk)

    def test_phone_penalty_screen_offers_it_without_waiting(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The phone penalty screen shows I'm sick immediately."""
        locker = create_locker(mock_tk, tmp_path)
        locker._show_phone_penalty("no phone")
        assert "I'm sick" in _button_texts(mock_tk)

    def test_relaxed_prompt_and_retry_offer_it(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Both the relaxed-day prompt and its retry screen show I'm sick."""
        locker = create_locker_relaxed_day(mock_tk, tmp_path)
        locker._start_relaxed_day_flow()
        assert "I'm sick" in _button_texts(mock_tk)
        mock_tk.Button.reset_mock()
        locker._show_relaxed_retry("nothing", "no_workout")
        assert "I'm sick" in _button_texts(mock_tk)


class TestTap:
    """What tapping I'm sick does on success and on refusal."""

    def test_success_marks_lifts_pushes_records_and_unlocks(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A successful tap marks sick, applies the floor, pushes, records and closes."""
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
        """A refused tap keeps the lock, shows the reason and offers a Back button."""
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
        assert [back.kwargs["command"]] == [locker._start_phone_check]

    def test_refusal_on_the_relaxed_prompt_goes_back_to_it(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """From the relaxed prompt a refusal's Back button returns to that prompt."""
        locker = create_locker_relaxed_day(mock_tk, tmp_path)
        locker._show_sick_refused("nope")
        back = next(
            c for c in mock_tk.Button.call_args_list if c.kwargs.get("text") == "Back"
        )
        assert [back.kwargs["command"]] == [locker._start_relaxed_day_flow]
