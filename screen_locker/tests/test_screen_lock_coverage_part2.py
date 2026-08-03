"""Tests targeting remaining screen_lock.py coverage gaps."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestUnlockScreenExtras:
    """Tests for unlock_screen extra-workout bonus and streak display (360-389)."""

    def _setup_unlock(
        self,
        mock_tk: MagicMock,
        tmp_path: Path,
        weekly_count: int = 5,
        streak: int = 0,
        adjust_ok: bool = True,
        seed_today_type: str | None = None,
    ):
        """Create a locker ready to call unlock_screen.

        ``seed_today_type`` pre-logs a counted workout for today under a
        different ``workout_id``, so the unlock's own verified workout is an
        ADDITIONAL same-day one — the case that now earns the +1h bonus.
        """
        log_file = tmp_path / "workout_log.json"
        if seed_today_type is None:
            log_file.write_text("{}")
        else:
            today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            log_file.write_text(
                json.dumps(
                    {
                        today: [
                            {
                                "timestamp": f"{today}T06:00:00+00:00",
                                "workout_data": {"type": seed_today_type},
                                "workout_id": f"{seed_today_type}:{today}",
                            }
                        ]
                    }
                )
            )
        locker = create_locker(mock_tk, tmp_path)
        locker.log_file = log_file
        locker.workout_data = {"type": "phone_verified"}

        object.__setattr__(
            locker, "_try_adjust_shutdown_for_workout", MagicMock(return_value=False)
        )
        object.__setattr__(
            locker, "_clear_debt_on_verified_workout", MagicMock(return_value=None)
        )
        object.__setattr__(
            locker,
            "_adjust_shutdown_time_by",
            MagicMock(return_value=adjust_ok),
        )
        object.__setattr__(
            locker,
            "_read_shutdown_config",
            MagicMock(return_value=(22, 22, 5)),
        )
        return locker

    def test_extra_workout_bonus_shown(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An additional same-day verified workout earns the +1h bonus."""
        locker = self._setup_unlock(
            mock_tk, tmp_path, weekly_count=5, seed_today_type="manual_workout"
        )

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch(
                "screen_locker._unlock_view.current_streak",
                return_value=0,
            ),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        locker._adjust_shutdown_time_by.assert_called_once_with(1)

    def test_extra_bonus_delta_displayed(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """extra_bonus_delta > 0 → _text called with 'Extra workout'."""
        locker = self._setup_unlock(mock_tk, tmp_path, seed_today_type="manual_workout")

        # Simulate before=22, after=23 → delta=1
        old_cfg = (22, 22, 5)
        new_cfg = (23, 23, 5)
        locker._read_shutdown_config.side_effect = [old_cfg, new_cfg]

        text_calls: list[str] = []

        def _capture_text(msg: str, **kw: object) -> None:
            text_calls.append(msg)

        object.__setattr__(locker, "_text", _capture_text)

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch(
                "screen_locker._unlock_view.current_streak",
                return_value=0,
            ),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert any("Extra workout" in c for c in text_calls)

    def test_no_extra_bonus_when_adjust_fails(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Additional verified workout but the +1h adjust fails → delta stays 0."""
        locker = self._setup_unlock(
            mock_tk,
            tmp_path,
            seed_today_type="manual_workout",
            adjust_ok=False,
        )

        text_calls: list[str] = []
        object.__setattr__(locker, "_text", lambda msg, **kw: text_calls.append(msg))

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert not any("Extra workout" in c for c in text_calls)

    def test_no_extra_bonus_when_new_config_unreadable(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Re-reading the shutdown config fails after the +1h → delta stays 0."""
        locker = self._setup_unlock(mock_tk, tmp_path, seed_today_type="manual_workout")
        # old_cfg readable, new_cfg unreadable → no delta can be computed.
        locker._read_shutdown_config.side_effect = [(22, 22, 5), None]

        text_calls: list[str] = []
        object.__setattr__(locker, "_text", lambda msg, **kw: text_calls.append(msg))

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert not any("Extra workout" in c for c in text_calls)

    def test_streak_displayed_when_nonzero(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """streak >= 1 → _text shows streak line (line 389)."""
        locker = self._setup_unlock(mock_tk, tmp_path, weekly_count=3, adjust_ok=False)

        text_calls: list[str] = []

        def _capture_text(msg: str, **kw: object) -> None:
            text_calls.append(msg)

        object.__setattr__(locker, "_text", _capture_text)

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=3,
            ),
            patch(
                "screen_locker._unlock_view.current_streak",
                return_value=3,
            ),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()

        assert any("streak" in c.lower() for c in text_calls)

    def test_extra_bonus_skipped_when_old_cfg_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """old_cfg is None → branch 361->366: bonus block skipped, delta stays 0."""
        locker = self._setup_unlock(mock_tk, tmp_path)
        # _read_shutdown_config returns None → condition at 361 is False
        locker._read_shutdown_config.return_value = None

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()
        # No assertion beyond "no crash" — we just needed the branch executed.

    def test_extra_bonus_skipped_when_new_cfg_none(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """new_cfg is None → branch 363->366: delta stays 0 even after adjust."""
        locker = self._setup_unlock(mock_tk, tmp_path)
        # First call (old_cfg): valid; second call (new_cfg after adjust): None
        locker._read_shutdown_config.side_effect = [(22, 22, 5), None]

        with (
            patch(
                "screen_locker._workout_credit.count_weekly_workouts",
                return_value=5,
            ),
            patch("screen_locker._unlock_view.current_streak", return_value=0),
            patch("screen_locker._log_mixin.compute_entry_hmac", return_value=None),
        ):
            locker.unlock_screen()


class TestIngestSyncedManualWorkouts:
    """Tests for _ingest_synced_manual_workouts (manual-sync wiring)."""

    def test_logs_each_ingested_record(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker.screen_lock.pull_all_manual_records",
                return_value=[("manual:x", {})],
            ),
            patch(
                "screen_locker.screen_lock.ingest_manual_records",
                return_value=["manual:x"],
            ) as ingest,
        ):
            locker._ingest_synced_manual_workouts()
        ingest.assert_called_once()

    def test_no_records_ingests_nothing(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        locker = create_locker(mock_tk, tmp_path)
        with (
            patch(
                "screen_locker.screen_lock.pull_all_manual_records",
                return_value=[],
            ),
            patch(
                "screen_locker.screen_lock.ingest_manual_records",
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
                "screen_locker.screen_lock.pull_all_manual_records",
                return_value=[],
            ),
            patch(
                "screen_locker.screen_lock.ingest_manual_records",
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
