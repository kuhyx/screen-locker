"""Future-dated records at the ingest chokepoint: deferred, then credited on the day."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from screen_locker._manual_sync import ingest_manual_records
from screen_locker.tests.test_manual_sync import (
    _OTHER_DRAFT,
    _TT_DRAFT,
    _manual_record,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_TODAY = "2026-10-16"
_TOMORROW = "2026-10-17"


def _days(log_file: Path) -> dict[str, int]:
    """Return ``{day: entry count}`` of the log, or {} if it does not exist."""
    if not log_file.exists():
        return {}
    return {d: len(e) for d, e in json.loads(log_file.read_text()).items()}


class TestDeferral:
    """A record dated after today stays in the sync store and earns nothing."""

    def test_a_future_record_is_not_ingested_or_credited(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        log_file = tmp_path / "log.json"
        calls: list[dict] = []
        with caplog.at_level(logging.INFO):
            ingested = ingest_manual_records(
                log_file,
                [_manual_record(_TT_DRAFT, _TOMORROW)],
                today=_TODAY,
                on_ingested=lambda entry, _prior: calls.append(entry),
            )
        assert ingested == []
        assert calls == []
        assert _days(log_file) == {}
        assert "deferred" in caplog.text

    def test_the_same_record_is_ingested_and_credited_on_its_day(
        self, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "log.json"
        record = _manual_record(_TT_DRAFT, _TOMORROW)
        calls: list[dict] = []

        assert ingest_manual_records(log_file, [record], today=_TODAY) == []
        ingested = ingest_manual_records(
            log_file,
            [record],
            today=_TOMORROW,
            on_ingested=lambda entry, _prior: calls.append(entry),
        )

        assert ingested == [record[0]]
        assert [c["workout_id"] for c in calls] == [record[0]]
        assert _days(log_file) == {_TOMORROW: 1}

    def test_a_garbled_date_is_skipped_loudly(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        record_id, payload = _manual_record(_TT_DRAFT, _TODAY)
        payload["date"] = "2026-13-99"
        with caplog.at_level(logging.WARNING):
            assert (
                ingest_manual_records(
                    tmp_path / "log.json", [(record_id, payload)], today=_TODAY
                )
                == []
            )
        assert "unparsable date" in caplog.text

    def test_an_empty_batch_touches_nothing(self, tmp_path: Path) -> None:
        assert ingest_manual_records(tmp_path / "log.json", [], today=_TODAY) == []
        assert not (tmp_path / "log.json").exists()

    def test_a_non_manual_record_is_ignored(self, tmp_path: Path) -> None:
        assert (
            ingest_manual_records(
                tmp_path / "log.json", [("s", {"exercises": []})], today=_TODAY
            )
            == []
        )

    def test_defaults_to_the_real_local_day(self, tmp_path: Path) -> None:
        record = _manual_record(_TT_DRAFT, "2999-01-01")
        assert ingest_manual_records(tmp_path / "log.json", [record]) == []


class TestBudgetAgainstTheWorkoutDate:
    """The budget is per workout date and counts pending future records."""

    def test_a_pending_record_does_not_reject_itself_on_its_day(
        self, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "log.json"
        mine = _manual_record(_TT_DRAFT, _TOMORROW)
        later = _manual_record(_OTHER_DRAFT, "2026-10-18")

        ingested = ingest_manual_records(log_file, [mine, later], today=_TOMORROW)

        assert ingested == [mine[0]]
        assert _days(log_file) == {_TOMORROW: 1}

    def test_other_pending_records_hold_slots_against_a_due_one(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Three records inside one 7-day window: whichever comes due while the
        # other two are still pending would be the third, so it is refused.
        log_file = tmp_path / "log.json"
        due = _manual_record(_TT_DRAFT, _TOMORROW)
        pending = [
            _manual_record(_OTHER_DRAFT, "2026-10-18"),
            _manual_record(
                _OTHER_DRAFT.__class__(
                    **{
                        **_OTHER_DRAFT.__dict__,
                        "start_time": "11:00",
                        "end_time": "12:00",
                    }
                ),
                "2026-10-19",
            ),
        ]
        with caplog.at_level(logging.INFO):
            ingested = ingest_manual_records(log_file, [due, *pending], today=_TOMORROW)
        assert ingested == []
        assert "budget exhausted" in caplog.text

    def test_a_logged_week_blocks_a_due_record_inside_it(self, tmp_path: Path) -> None:
        log_file = tmp_path / "log.json"
        for day, draft in (("2026-10-12", _TT_DRAFT), ("2026-10-13", _OTHER_DRAFT)):
            assert ingest_manual_records(
                log_file, [_manual_record(draft, day)], today=day
            )
        blocked = _manual_record(_TT_DRAFT, _TODAY)
        assert ingest_manual_records(log_file, [blocked], today=_TODAY) == []
        assert _days(log_file) == {"2026-10-12": 1, "2026-10-13": 1}
