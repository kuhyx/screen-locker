"""Tests for the read-only status snapshot layer in _status_data.py."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Fixed reference instant: Friday 2024-01-05, 12:00 UTC == 13:00 Europe/Warsaw.
# Outside the 05:00-09:00 early-bird window and not a Tue/Wed/Thu relaxed day,
# so lock-decision branches are fully deterministic regardless of wall clock.
_FRIDAY_NOON_UTC = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
# Monday of that same ISO week, for Mon-Wed shutdown-band assertions.
_MONDAY_NOON_UTC = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


def _files(tmp_path: Path) -> dict[str, Path]:
    return {
        "log_file": tmp_path / "workout_log.json",
        "extra_benefits_file": tmp_path / "extra_benefits_state.json",
        "shutdown_base_file": tmp_path / "shutdown_base.json",
        "shutdown_config_file": tmp_path / "shutdown_config.conf",
        "scheduled_skips_file": tmp_path / "scheduled_skips.json",
        "early_bird_pending_file": tmp_path / "early_bird_pending.json",
    }
