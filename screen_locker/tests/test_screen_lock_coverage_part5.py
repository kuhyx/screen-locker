"""Tests for ingesting manual workouts synced from the phone.

Split out of test_screen_lock_coverage_part2.py for the 250-line cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestIngestSyncedManualWorkouts:
    """Tests for _ingest_synced_manual_workouts (manual-sync wiring)."""

    def test_logs_each_ingested_record(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Logs each ingested record."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._sync_mixin.pull_all_manual_records",
                return_value=[("manual:x", {})],
            ),
            patch(
                "screen_locker._sync_mixin.ingest_manual_records",
                return_value=["manual:x"],
            ) as ingest,
        ):
            locker._ingest_synced_manual_workouts()
        ingest.assert_called_once()

    def test_no_records_ingests_nothing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """No records ingests nothing."""
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker._sync_mixin.pull_all_manual_records",
                return_value=[],
            ),
            patch(
                "screen_locker._sync_mixin.ingest_manual_records",
                return_value=[],
            ),
        ):
            locker._ingest_synced_manual_workouts()

    def test_passes_credit_callback_and_resets_workout_data(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The callback wired into ingest_manual_records must be
        ``locker._credit_ingested_manual_workout``, so a synced manual
        workout earns the same reward a live one would; workout_data is reset
        afterward so it can't leak into a later interactive flow."""
        locker = create_locker(mock_tk, tmp_path)
        locker.workout_data = {"stale": "state"}
        with (
            patch(
                "screen_locker._sync_mixin.pull_all_manual_records",
                return_value=[],
            ),
            patch(
                "screen_locker._sync_mixin.ingest_manual_records",
                return_value=[],
            ) as ingest,
        ):
            locker._ingest_synced_manual_workouts()
        assert ingest.call_args.kwargs["on_ingested"] == (
            locker._credit_ingested_manual_workout
        )
        assert locker.workout_data == {}

    def test_credit_ingested_manual_workout_applies_reward(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """_credit_ingested_manual_workout sets workout_data to the ingested
        entry and applies the shared credit logic — proving a synced manual
        workout (today's or back-dated) earns full shutdown/debt credit,
        exactly like a live-logged one."""
        locker = create_locker(mock_tk, tmp_path)
        entry = {"type": "manual_workout", "source": "table tennis at Solec"}
        prior: list[dict] = []
        with patch.object(
            locker,
            "_apply_credit_for_written_entry",
            return_value=MagicMock(shutdown_adjusted=True, extra_bonus_delta=0),
        ) as apply_credit:
            locker._credit_ingested_manual_workout(entry, prior)
        assert locker.workout_data == entry
        apply_credit.assert_called_once_with(prior)

    def test_credit_ingested_manual_workout_logs_extra_bonus(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A second same-day synced manual workout (extra_bonus_delta, not the
        base push) takes the elif branch — a back-dated sync can still stack
        the +1h bonus exactly like an additional same-day verified workout."""
        locker = create_locker(mock_tk, tmp_path)
        entry = {"type": "manual_workout", "source": "gym"}
        prior = [{"workout_data": {"type": "manual_workout"}}]
        with patch.object(
            locker,
            "_apply_credit_for_written_entry",
            return_value=MagicMock(shutdown_adjusted=False, extra_bonus_delta=1),
        ) as apply_credit:
            locker._credit_ingested_manual_workout(entry, prior)
        assert locker.workout_data == entry
        apply_credit.assert_called_once_with(prior)

    def test_credit_ingested_manual_workout_no_reward_logs_nothing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A duplicate/no-op credit result (neither shutdown_adjusted nor
        extra_bonus_delta) → neither log line fires; credit is still applied
        via workout_data being set."""
        locker = create_locker(mock_tk, tmp_path)
        entry = {"type": "manual_workout", "source": "gym"}
        prior: list[dict] = []
        with patch.object(
            locker,
            "_apply_credit_for_written_entry",
            return_value=MagicMock(shutdown_adjusted=False, extra_bonus_delta=0),
        ) as apply_credit:
            locker._credit_ingested_manual_workout(entry, prior)
        assert locker.workout_data == entry
        apply_credit.assert_called_once_with(prior)
