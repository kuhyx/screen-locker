"""Tests for the lock around the workout-log write chokepoint.

The 5-minute locker pass, the 15-minute sync and the RunnerUp upload watcher
can backfill the same run at the same moment. Without the lock each one reads
the log before the others wrote, sees the run missing, appends it and earns
its own shutdown credit.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker import _log_mixin
from screen_locker._log_io import load_workout_log
from screen_locker._log_mixin import write_signed_entry

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_RUN = {"type": "runnerup_verified", "distance_km": 4.7, "duration_minutes": 54.0}
_WRITERS = 4


def _slow_loader(log_file: Path) -> dict:
    """Load the log, then stall so racing writers all read before any writes."""
    logs = load_workout_log(log_file)
    time.sleep(0.05)
    return logs


class TestWriteLock:
    """write_signed_entry serialises its read-dedup-write across writers."""

    def test_racing_writers_record_the_run_once(self, tmp_path: Path) -> None:
        """Concurrent appends of one run yield one entry and one ``appended``.

        flock conflicts between separate open() calls even inside one
        process, so threads exercise the same lock the separate systemd
        passes contend on.
        """
        log_file = tmp_path / "log.json"
        barrier = threading.Barrier(_WRITERS)
        appended: list[bool] = []

        def writer() -> None:
            barrier.wait()
            appended.append(write_signed_entry(log_file, "2026-10-07", _RUN).appended)

        with patch.object(_log_mixin, "load_workout_log", _slow_loader):
            threads = [threading.Thread(target=writer) for _ in range(_WRITERS)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert sorted(appended) == [False] * (_WRITERS - 1) + [True]
        assert len(load_workout_log(log_file)["2026-10-07"]) == 1

    def test_unlockable_log_warns_and_still_writes(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A lock file that cannot be opened is a warning, not a lost workout."""
        log_file = tmp_path / "log.json"
        log_file.with_suffix(".lock").mkdir()  # open("a") on a dir -> OSError

        with caplog.at_level(logging.WARNING):
            result = write_signed_entry(log_file, "2026-10-07", _RUN)

        assert result.appended is True
        assert len(load_workout_log(log_file)["2026-10-07"]) == 1
        assert "Could not lock workout log" in caplog.text
