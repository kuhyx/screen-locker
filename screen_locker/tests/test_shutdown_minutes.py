"""Minute-precision shutdown schedule: legacy keys and the real command line.

The schedule moved from whole hours to minutes after midnight. Pinned here:
``read_shutdown_config`` still understands a file with only the old ``*_HOUR``
keys, the sick-day state still loads its old ``original_*_hour`` keys, and a
value that is not a whole hour (a 30-minute earner) reaches the helper script
as ``HH:MM`` rather than being floored.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker._shutdown import read_shutdown_config
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestReadShutdownConfigKeys:
    """``*_MINUTES`` is authoritative; ``*_HOUR`` is only a fallback."""

    def _read(self, tmp_path: Path, body: str) -> tuple[int, int, int] | None:
        conf = tmp_path / "shutdown.conf"
        conf.write_text(body)
        return read_shutdown_config(conf)

    def test_minutes_keys_are_read_exactly(self, tmp_path: Path) -> None:
        body = "MON_WED_MINUTES=1110\nTHU_SUN_MINUTES=1230\nMORNING_END_MINUTES=330\n"
        assert self._read(tmp_path, body) == (1110, 1230, 330)

    def test_legacy_hour_only_file_reads_as_hours_times_sixty(
        self, tmp_path: Path
    ) -> None:
        body = "MON_WED_HOUR=21\nTHU_SUN_HOUR=20\nMORNING_END_HOUR=5\n"
        assert self._read(tmp_path, body) == (1260, 1200, 300)

    def test_minutes_win_over_the_rounded_hour_copy(self, tmp_path: Path) -> None:
        """A dual-key file's *_HOUR is strict-rounded: 18:30 -> 18, 05:30 -> 6."""
        body = (
            "MON_WED_MINUTES=1110\nTHU_SUN_MINUTES=1110\nMORNING_END_MINUTES=330\n"
            "MON_WED_HOUR=18\nTHU_SUN_HOUR=18\nMORNING_END_HOUR=6\n"
        )
        assert self._read(tmp_path, body) == (1110, 1110, 330)

    def test_keys_resolve_independently(self, tmp_path: Path) -> None:
        """One key in minutes, the others only in hours: each falls back alone."""
        body = "MON_WED_MINUTES=1110\nTHU_SUN_HOUR=20\nMORNING_END_HOUR=5\n"
        assert self._read(tmp_path, body) == (1110, 1200, 300)

    def test_a_missing_value_is_none(self, tmp_path: Path) -> None:
        body = "MON_WED_MINUTES=1110\nTHU_SUN_MINUTES=1110\n"
        assert self._read(tmp_path, body) is None

    def test_non_numeric_values_and_comments_are_ignored(self, tmp_path: Path) -> None:
        body = (
            "# MON_WED_MINUTES=1\nMON_WED_MINUTES=oops\nMON_WED_HOUR=21\n"
            "THU_SUN_HOUR=20\nMORNING_END_HOUR=5\nno-equals-sign\n"
        )
        assert self._read(tmp_path, body) == (1260, 1200, 300)


class TestLegacySickDayState:
    """A state file written before the migration still restores correctly."""

    def _load(
        self, tmp_path: Path, state: dict[str, object]
    ) -> tuple[str, int, int] | None:
        locker = create_locker(MagicMock(), tmp_path)
        state_file = tmp_path / "sick.json"
        state_file.write_text(json.dumps(state))
        with patch(
            "screen_locker._shutdown_sick_state.SICK_DAY_STATE_FILE", state_file
        ):
            return locker._load_sick_day_state()

    def test_legacy_hour_keys_are_read_as_minutes(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        state = {"date": "2026-10-03", "original_mon_wed_hour": 21}
        state["original_thu_sun_hour"] = 20
        assert self._load(tmp_path, state) == ("2026-10-03", 1260, 1200)

    def test_minutes_keys_win_over_legacy_keys(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        state = {
            "date": "2026-10-03",
            "original_mon_wed_minutes": 1290,
            "original_mon_wed_hour": 21,
            "original_thu_sun_minutes": 1200,
        }
        assert self._load(tmp_path, state) == ("2026-10-03", 1290, 1200)

    def test_a_missing_band_is_none(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        state = {"date": "2026-10-03", "original_mon_wed_hour": 21}
        assert self._load(tmp_path, state) is None


@pytest.mark.usefixtures("pre_ladder")
class TestMinutesReachTheHelperScript:
    """The helper receives HH:MM, so a half hour is not floored on the way."""

    def _run(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        config: tuple[int, int, int],
        action: str,
        *args: int,
    ) -> list[str]:
        locker = create_locker(mock_tk, tmp_path)
        script = tmp_path / "adjust.sh"
        script.write_text("")
        done = MagicMock(stdout="ok")
        with (
            patch.object(locker, "_read_shutdown_config", return_value=config),
            patch("screen_locker._shutdown.ADJUST_SHUTDOWN_SCRIPT", script),
            patch("screen_locker._shutdown.subprocess.run", return_value=done) as run,
        ):
            assert getattr(locker, action)(*args) is True
        cmd: list[str] = run.call_args.args[0]
        return cmd[2:]

    def test_a_30_minute_bonus_becomes_18_30(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        args = self._run(
            mock_tk, tmp_path, (1080, 1080, 300), "_adjust_shutdown_time_by", 30
        )
        assert args == ["--restore", "18:30", "18:30", "05:00"]

    def test_the_bonus_is_capped_at_24_00(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        args = self._run(
            mock_tk, tmp_path, (1380, 1380, 300), "_adjust_shutdown_time_by", 90
        )
        assert args == ["--restore", "24:00", "24:00", "05:00"]

    @pytest.mark.parametrize(
        ("config", "expected"),
        [
            ((1290, 1260, 300), ["--restore", "23:00", "23:00", "05:00"]),
            ((1080, 1080, 300), ["--restore", "20:00", "20:00", "05:00"]),
        ],
    )
    def test_workout_reward_is_clamped_to_23_00(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        config: tuple[int, int, int],
        expected: list[str],
    ) -> None:
        args = self._run(mock_tk, tmp_path, config, "_adjust_shutdown_time_later")
        assert args == expected

    @pytest.mark.parametrize(
        ("config", "expected"),
        [
            ((1290, 1290, 300), ["20:30", "20:30", "05:00"]),
            ((1100, 1085, 300), ["18:00", "18:00", "05:00"]),
        ],
    )
    def test_sick_day_steps_back_an_hour_but_not_before_18_00(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        config: tuple[int, int, int],
        expected: list[str],
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        script = tmp_path / "adjust.sh"
        script.write_text("")
        with (
            patch.object(locker, "_read_shutdown_config", return_value=config),
            patch.object(locker, "_save_sick_day_state", return_value=True),
            patch("screen_locker._shutdown.ADJUST_SHUTDOWN_SCRIPT", script),
            patch("screen_locker._shutdown.subprocess.run") as run,
        ):
            assert locker._apply_earlier_shutdown("2026-10-04") is True
        assert run.call_args.args[0][2:] == expected
