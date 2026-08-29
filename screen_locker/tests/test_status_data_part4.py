"""Tests for the read-only status snapshot layer in _status_data.py."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from screen_locker._status_data import format_summary_line, gather_status
from screen_locker.tests.test_status_data import _files

if TYPE_CHECKING:
    from pathlib import Path

# Fixed reference instant: Friday 2024-01-05, 12:00 UTC == 13:00 Europe/Warsaw.
# Outside the 05:00-09:00 early-bird window and not a Tue/Wed/Thu relaxed day,
# so lock-decision branches are fully deterministic regardless of wall clock.
_FRIDAY_NOON_UTC = datetime(2024, 1, 5, 12, 0, tzinfo=UTC)
# Monday of that same ISO week, for Mon-Wed shutdown-band assertions.
_MONDAY_NOON_UTC = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


class TestFormatSummaryLine:
    """format_summary_line variants."""

    def test_checkmark_when_week_complete(self, tmp_path: Path) -> None:
        """Checkmark when week complete."""
        files = _files(tmp_path)
        files["log_file"].write_text(
            json.dumps(
                {
                    d: {"workout_data": {"type": "phone_verified"}}
                    for d in (
                        "2024-01-01",
                        "2024-01-02",
                        "2024-01-03",
                        "2024-01-04",
                        "2024-01-05",
                    )
                }
            )
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert format_summary_line(snap).startswith("✓")

    def test_ellipsis_when_week_incomplete(self, tmp_path: Path) -> None:
        """Ellipsis when week incomplete."""
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert format_summary_line(snap).startswith("…")

    def test_question_mark_when_no_shutdown_config(self, tmp_path: Path) -> None:
        """Question mark when no shutdown config."""
        files = _files(tmp_path)
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert "?:00 tonight" not in format_summary_line(snap)
        assert "? tonight" in format_summary_line(snap)

    def test_mon_wed_band_used_on_monday(self, tmp_path: Path) -> None:
        """Mon wed band used on monday."""
        files = _files(tmp_path)
        files["shutdown_config_file"].write_text(
            "MON_WED_HOUR=20\nTHU_SUN_HOUR=23\nMORNING_END_HOUR=5\n"
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_MONDAY_NOON_UTC)

        assert "20:00 tonight" in format_summary_line(snap)

    def test_thu_sun_band_used_on_friday(self, tmp_path: Path) -> None:
        """Thu sun band used on friday."""
        files = _files(tmp_path)
        files["shutdown_config_file"].write_text(
            "MON_WED_HOUR=20\nTHU_SUN_HOUR=23\nMORNING_END_HOUR=5\n"
        )
        with patch(
            "screen_locker._status_data.has_workout_skip_today", return_value=False
        ):
            snap = gather_status(**files, now=_FRIDAY_NOON_UTC)

        assert "23:00 tonight" in format_summary_line(snap)
