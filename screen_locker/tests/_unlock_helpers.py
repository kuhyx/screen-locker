"""Shared factory for unlock_screen tests.

Extracted from test_screen_lock_coverage_part2.py when it was split for the
250-line cap, so both halves build their locker the same way. Named with a
leading underscore so pre-commit's name-tests-test hook skips it.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


def setup_unlock(
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
