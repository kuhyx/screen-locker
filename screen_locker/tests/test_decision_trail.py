"""Tests for _decision_trail: collapsing repeats so a storm cannot wipe history.

On 2026-08-30 the locker had no X server at 02:00, crashed, was restarted by
``Restart=on-failure`` every ~6.3s, and wrote ~1693 identical records in three
hours. At ``DECISION_LOG_MAX_ENTRIES = 3000`` that evicted everything behind
them: the tool built to make blind spots impossible erased its own history.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker._decision_trail import append_record

if TYPE_CHECKING:
    from pathlib import Path


def _rows(target: Path) -> list[dict[str, object]]:
    """Return the trail as parsed records.

    Args:
        target: The trail file.

    Returns:
        One dict per line, oldest first.
    """
    return [json.loads(line) for line in target.read_text().splitlines() if line]


def _record(index: int, *, reason: str = "enforced") -> dict[str, object]:
    """Build one record whose only varying field is its timestamp.

    Args:
        index: Distinguishes the timestamps.
        reason: The decision reason.

    Returns:
        A record ready for append_record.
    """
    return {
        "timestamp": f"2026-08-30T02:{index:02d}:00+00:00",
        "locked": True,
        "reason": reason,
    }


class TestCollapsing:
    """Consecutive identical events become one row, not N."""

    def test_a_storm_of_identical_records_stays_one_row(self, tmp_path: Path) -> None:
        """The 1695-restart loop, in miniature."""
        target = tmp_path / "d.jsonl"
        for i in range(50):
            append_record(_record(i), log_file=target)
        rows = _rows(target)
        assert len(rows) == 1
        assert rows[0]["repeat_count"] == 50

    def test_the_row_keeps_both_ends_of_the_streak(self, tmp_path: Path) -> None:
        """`timestamp` is when it began; `last_timestamp` is freshness."""
        target = tmp_path / "d.jsonl"
        append_record(_record(0), log_file=target)
        append_record(_record(7), log_file=target)
        row = _rows(target)[0]
        assert row["timestamp"] == "2026-08-30T02:00:00+00:00"
        assert row["last_timestamp"] == "2026-08-30T02:07:00+00:00"

    def test_a_different_decision_opens_a_new_row(self, tmp_path: Path) -> None:
        """Collapsing must never hide a change of outcome."""
        target = tmp_path / "d.jsonl"
        append_record(_record(0), log_file=target)
        append_record(_record(1, reason="weekly_minimum_met"), log_file=target)
        assert len(_rows(target)) == 2

    def test_only_consecutive_records_collapse(self, tmp_path: Path) -> None:
        """An intervening event ends the streak, as the history shows it must."""
        target = tmp_path / "d.jsonl"
        append_record(_record(0), log_file=target)
        append_record(_record(1, reason="mode_makes_no_decision"), log_file=target)
        append_record(_record(2), log_file=target)
        rows = _rows(target)
        assert len(rows) == 3
        assert all("repeat_count" not in row for row in rows)

    def test_a_changed_field_is_not_a_repeat(self, tmp_path: Path) -> None:
        """Everything but the timestamps must match to collapse."""
        target = tmp_path / "d.jsonl"
        append_record(_record(0), log_file=target)
        append_record({**_record(1), "weekly_count": 4}, log_file=target)
        assert len(_rows(target)) == 2


class TestCorruptTrail:
    """A trail that cannot be parsed is kept, loudly -- never overwritten."""

    def test_an_unparsable_tail_starts_a_new_row(
        self, tmp_path: Path, caplog: MagicMock
    ) -> None:
        """Overwriting a line we cannot read would destroy real history."""
        target = tmp_path / "d.jsonl"
        target.write_text("{truncated\n", encoding="utf-8")
        append_record(_record(0), log_file=target)
        lines = target.read_text().splitlines()
        assert lines[0] == "{truncated"
        assert len(lines) == 2
        assert "unparsable" in caplog.text

    def test_a_non_object_tail_starts_a_new_row(self, tmp_path: Path) -> None:
        """Valid JSON of the wrong shape is not a record to merge into."""
        target = tmp_path / "d.jsonl"
        target.write_text('["not", "a", "record"]\n', encoding="utf-8")
        append_record(_record(0), log_file=target)
        assert len(target.read_text().splitlines()) == 2

    def test_a_write_failure_is_reported(
        self, tmp_path: Path, caplog: MagicMock
    ) -> None:
        """A gap in the trail must itself be visible."""
        target = tmp_path / "nested" / "d.jsonl"
        with patch(
            "screen_locker._decision_trail.Path.write_text",
            side_effect=OSError("full"),
        ):
            append_record(_record(0), log_file=target)
        assert "durable trail now has a gap" in caplog.text
