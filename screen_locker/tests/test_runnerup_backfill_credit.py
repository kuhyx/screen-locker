"""The RunnerUp backfill credits each fill through the shared ``on_ingested``.

Regression for 2026-09-16: a run synced off the phone at 20:25 was appended
to the log but earned only the weekly-surplus bonus (+1h per workout above
the weekly minimum), which was 0 that early in the week -- the shutdown hour
stayed at 20:00 while the daily base reset would have derived 22:00 from the
very same log. Every fill now goes through the same credit callback as a
synced manual workout or StrongLifts session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._log_io import load_workout_log
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

_RUN = {"sport": 0, "duration_seconds": 4200, "distance_m": 5800}


def _stub_phone(locker: object, dates: set[str]) -> None:
    """Make the scan see one verified run on each of ``dates``."""
    object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
    object.__setattr__(
        locker,
        "_find_runnerup_exports_for_date",
        MagicMock(side_effect=lambda d: ["/sdcard/run.tcx"] if d in dates else []),
    )
    object.__setattr__(locker, "_pull_and_parse_tcx", MagicMock(return_value=_RUN))
    object.__setattr__(
        locker, "_validate_runnerup_data", MagicMock(return_value=("verified", "ok"))
    )


class TestBackfillCreditCallback:
    """``_try_fill_runnerup_for_date`` / ``_scan_and_fill_week_runnerup``."""

    def test_callback_gets_workout_data_and_prior_entries(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The callback sees the appended entry and that day's prior entries."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text(
            '{"2026-09-16": [{"workout_data": {"type": "manual_workout"}}]}'
        )
        _stub_phone(locker, {"2026-09-16"})
        seen: list[tuple[dict, list[dict]]] = []

        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"):
            appended = locker._try_fill_runnerup_for_date(
                "2026-09-16", log_file, lambda e, p: seen.append((e, p))
            )

        assert appended is True
        assert len(seen) == 1
        entry, prior = seen[0]
        assert entry["type"] == "runnerup_verified"
        assert entry["distance_km"] == 5.8
        assert [e["workout_data"]["type"] for e in prior] == ["manual_workout"]

    def test_duplicate_fill_does_not_fire_callback(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A re-scan of an already-logged run appends nothing and credits nothing."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        _stub_phone(locker, {"2026-09-16"})
        callback = MagicMock()

        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"):
            first = locker._try_fill_runnerup_for_date("2026-09-16", log_file, callback)
            second = locker._try_fill_runnerup_for_date(
                "2026-09-16", log_file, callback
            )

        assert (first, second) == (True, False)
        assert callback.call_count == 1
        assert len(load_workout_log(log_file)["2026-09-16"]) == 1

    def test_no_callback_still_appends(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Callers that only want the log filled (no reward) keep working."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        _stub_phone(locker, {"2026-09-16"})

        with patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"):
            assert locker._try_fill_runnerup_for_date("2026-09-16", log_file) is True

    def test_week_scan_passes_callback_to_every_fill(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The week scan forwards ``on_ingested`` to each day it fills."""
        locker = create_locker(mock_tk, tmp_path)
        log_file = tmp_path / "log.json"
        log_file.write_text("{}")
        fill = MagicMock(return_value=True)
        object.__setattr__(locker, "_has_adb_device", MagicMock(return_value=True))
        object.__setattr__(locker, "_try_fill_runnerup_for_date", fill)
        callback = MagicMock()

        filled = locker._scan_and_fill_week_runnerup(log_file, on_ingested=callback)

        assert filled == fill.call_count >= 1
        assert all(call.args[2] is callback for call in fill.call_args_list)


class TestSyncPassCreditsRunnerUp:
    """``_auto_fill_week_runnerup_bonus`` (the 15-minute timer path)."""

    def test_first_run_of_the_day_pushes_shutdown_two_hours(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Base 20:00 + today's first counted workout = 22:00 -- the day rule."""
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file.write_text("{}")
        _stub_phone(locker, {"2026-09-16"})
        object.__setattr__(
            locker,
            "_scan_and_fill_week_runnerup",
            lambda log, on_ingested=None: locker._try_fill_runnerup_for_date(
                "2026-09-16", log, on_ingested
            ),
        )
        config = {"hours": (20, 20, 5)}

        def write(mw: int, ts: int, me: int, restore: bool = False) -> bool:
            config["hours"] = (mw, ts, me)
            return True

        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(side_effect=lambda: config["hours"]),
        )
        object.__setattr__(
            locker, "_write_shutdown_config", MagicMock(side_effect=write)
        )

        with (
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value="sig"),
            patch("screen_locker._workout_credit._sick_tracker.load_history") as hist,
        ):
            hist.return_value.debt = 0
            locker._auto_fill_week_runnerup_bonus()
            locker._auto_fill_week_runnerup_bonus()

        assert config["hours"] == (22, 22, 5)
        assert locker.workout_data == {}
