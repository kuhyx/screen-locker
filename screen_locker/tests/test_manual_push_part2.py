"""Tests for push_pc_workouts.

Split out of test_manual_push.py for the 250-line cap; the shared _entry /
_write_log helpers stay in that module and are imported here.
"""
# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import FirebaseSyncError

from screen_locker import _manual_push
from screen_locker._manual_push import (
    PushResult,
    push_pc_workouts,
)
from screen_locker.tests.test_manual_push import _entry, _write_log

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_MANUAL = {
    "type": "manual_workout",
    "source": "table tennis at Solec",
    "start_time": "18:00",
    "rpe": 6,
}
_RUN = {
    "type": "runnerup_verified",
    "source": "Running: 9.8 km in 55 min",
    "distance_km": 9.8,
}


class TestPushPcWorkouts:
    """Every outcome is reported — never a silent no-op."""

    def test_no_firebase_config_reports_why(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No Firebase config: nothing pushed, the reason and count say so.

        The autouse ``_no_real_firebase_config`` fixture is exactly this
        machine state, so the real ``sync_client_or_reason`` runs here.
        """
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_RUN, "2026-07-13T10:00:00+00:00")]}
        )
        with caplog.at_level("WARNING"):
            result = push_pc_workouts(log_file)
        assert result.pushed is False
        assert result.record_count == 1
        assert result.reason.startswith("no Firebase config at ")
        assert "1 workout(s) stay local" in caplog.text

    def test_empty_log_reports_why(self, tmp_path: Path) -> None:
        """Empty log reports why."""
        log_file = tmp_path / "log.json"
        _write_log(log_file, {})
        with patch.object(_manual_push, "sync_client_or_reason") as build:
            result = push_pc_workouts(log_file)
        build.assert_not_called()
        assert result.pushed is False
        assert result.record_count == 0
        assert "no counted workouts" in result.reason

    def test_sync_error_reports_why(self, tmp_path: Path) -> None:
        """Sync error reports why."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_RUN, "2026-07-13T10:00:00+00:00")]}
        )
        with (
            patch.object(
                _manual_push, "sync_client_or_reason", return_value=(MagicMock(), "")
            ),
            patch.object(
                _manual_push, "sync_log", side_effect=FirebaseSyncError("403 forbidden")
            ),
        ):
            result = push_pc_workouts(log_file)
        assert result.pushed is False
        assert result.record_count == 1
        assert "403 forbidden" in result.reason

    def test_network_error_is_not_blamed_on_the_token(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A network failure must not be reported as a permissions problem.

        Regression guard for 2026-07-20: the morning routine runs seconds after
        boot/resume, so its pushes failed with the network still down — and the
        log asserted "a 403 here means the token lacks contents:write", which
        sent an investigation chasing a permissions bug that did not exist.
        """
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_RUN, "2026-07-13T10:00:00+00:00")]}
        )
        with (
            patch.object(
                _manual_push, "sync_client_or_reason", return_value=(MagicMock(), "")
            ),
            patch.object(
                _manual_push,
                "sync_log",
                side_effect=FirebaseSyncError("network error reading x"),
            ),
            caplog.at_level("WARNING"),
        ):
            result = push_pc_workouts(log_file)
        assert result.pushed is False
        assert "network error reading x" in caplog.text
        assert "contents:write" not in caplog.text

    def test_successful_push_reports_count(self, tmp_path: Path) -> None:
        """Successful push reports count."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file,
            {
                "2026-07-13": [
                    _entry(_MANUAL, "2026-07-13T07:25:12+00:00"),
                    _entry(_RUN, "2026-07-13T23:10:00+00:00"),
                ]
            },
        )
        fake_sync = MagicMock()
        with (
            patch.object(
                _manual_push, "sync_client_or_reason", return_value=(MagicMock(), "")
            ),
            patch.object(_manual_push, "sync_log", fake_sync),
        ):
            result = push_pc_workouts(log_file)
        assert result == PushResult(pushed=True, record_count=2, reason="pushed")
        assert fake_sync.call_count == 1

    def test_pushes_runs_not_just_manuals(self, tmp_path: Path) -> None:
        """Regression: the phone must converge on the PC's runs too."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-12": [_entry(_RUN, "2026-07-12T10:00:00+00:00")]}
        )
        with (
            patch.object(
                _manual_push, "sync_client_or_reason", return_value=(MagicMock(), "")
            ),
            patch.object(_manual_push, "sync_log", MagicMock()) as fake_sync,
        ):
            push_pc_workouts(log_file)
        # local_log is the second positional arg since crdt-sync v0.9.0.
        pushed = fake_sync.call_args.args[1]
        assert "runnerup_verified:2026-07-12" in pushed


class TestPushLogsItsOutcome:
    """The journal line is what says a push landed; it must name Firebase."""

    def test_a_healthy_push_logs_the_count_and_no_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A clean push says how many records went to Firebase, at INFO."""
        log_file = tmp_path / "log.json"
        _write_log(
            log_file, {"2026-07-13": [_entry(_RUN, "2026-07-13T10:00:00+00:00")]}
        )
        with (
            patch.object(
                _manual_push, "sync_client_or_reason", return_value=(MagicMock(), "")
            ),
            patch.object(_manual_push, "with_sync_retry", MagicMock()),
            caplog.at_level("INFO"),
        ):
            result = push_pc_workouts(log_file)

        assert result == PushResult(pushed=True, record_count=1, reason="pushed")
        assert "Synced 1 workout(s) to Firebase" in caplog.text
        assert not [r for r in caplog.records if r.levelname == "WARNING"]
