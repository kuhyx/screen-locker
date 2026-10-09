"""Tests for ``_workout_ledger`` and its backfill CLI: one signed row per credit."""

from __future__ import annotations

from datetime import date, datetime, time
import json
import logging
from typing import TYPE_CHECKING, Any

import earned_time
import pytest

from screen_locker import _workout_ledger
from screen_locker._log_mixin import write_signed_entry
from screen_locker._workout_ledger import (
    append_rows,
    credit_row,
    entry_done_at,
    existing_rows,
    ledger_path,
    new_rows,
    rest_row,
)
from screen_locker.tests._earned_fixtures import KEY, signing_key

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_DAY = date(2026, 10, 4)
_ISO = _DAY.isoformat()


def local(hhmm: str, day: date = _DAY) -> float:
    hours, minutes = map(int, hhmm.split(":"))
    return datetime.combine(day, time(hours, minutes)).astimezone().timestamp()


@pytest.fixture
def key(tmp_path: Path) -> Iterator[Path]:
    with signing_key(tmp_path) as path:
        yield path


def entry(
    data: dict[str, Any], stamp: str = "2026-10-04T20:00:00+00:00", **extra: Any
) -> dict[str, Any]:
    return {"timestamp": stamp, "workout_data": data, **extra}


def ledger() -> list[dict[str, Any]]:
    return json.loads(ledger_path().read_text())["entries"]


class TestEntryDoneAt:
    def test_the_tcx_end_wins(self) -> None:
        done = entry({"type": "runnerup_verified", "completed_at": 123.5})
        assert entry_done_at(done, _DAY) == 123.5

    def test_a_numeric_string_and_iso_are_read(self) -> None:
        assert entry_done_at(entry({"completed_at": "77.5"}), _DAY) == 77.5
        iso = entry({"completed_at": "2026-10-04T10:00:00+00:00"})
        assert (
            entry_done_at(iso, _DAY)
            == datetime.fromisoformat("2026-10-04T10:00:00+00:00").timestamp()
        )

    def test_a_manual_end_time_is_on_its_day(self) -> None:
        manual = entry({"type": "manual_workout", "end_time": "18:40"})
        assert entry_done_at(manual, _DAY) == local("18:40")

    def test_a_pc_session_is_its_start_plus_duration(self) -> None:
        session = entry(
            {
                "type": "pc_workout_verified",
                "sync_record_id": "2026-10-04T15:42:00",
                "duration_minutes": "90.0",
            }
        )
        assert entry_done_at(session, _DAY) == local("17:12")

    def test_a_session_without_a_duration_falls_back_to_logging(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        session = entry(
            {"type": "pc_workout_verified", "sync_record_id": "2026-10-04T15:42:00"}
        )
        with caplog.at_level(logging.WARNING):
            done = entry_done_at(session, _DAY)
        assert done == datetime.fromisoformat("2026-10-04T20:00:00+00:00").timestamp()
        assert "no usable duration" in caplog.text

    def test_nothing_usable_is_none(self, caplog: pytest.LogCaptureFixture) -> None:
        bare = {"workout_data": "?", "timestamp": "never"}
        with caplog.at_level(logging.WARNING):
            assert entry_done_at(bare, _DAY) is None
        assert "Unusable workout time" in caplog.text


class TestCreditRow:
    def test_each_source_is_named(self) -> None:
        # No workout_id on the entry: the credit slot names the row.
        cases = {
            "runnerup_verified": ("runnerup_tcx", f"runnerup_verified:{_ISO}#0"),
            "phone_verified": ("stronglifts", f"stronglifts:{_ISO}"),
            "manual_workout": ("manual", f"manual_workout:{_ISO}#0"),
        }
        for wtype, (source, entry_id) in cases.items():
            row = credit_row(_ISO, [entry({"type": wtype})], 0)
            assert row is not None
            assert row["detail"]["source"] == source
            assert row["entry_id"] == entry_id

    def test_a_non_credit_has_no_row(self) -> None:
        assert credit_row(_ISO, [entry({"type": "relaxed_day_skip"})], 0) is None

    def test_both_stronglifts_paths_share_one_row_and_the_real_end(self) -> None:
        phone = entry({"type": "phone_verified"}, workout_id="phone_verified:x")
        pc = entry(
            {
                "type": "pc_workout_verified",
                "sync_record_id": "2026-10-04T15:42:00",
                "duration_minutes": "90",
            }
        )
        first = credit_row(_ISO, [phone, pc], 0)
        second = credit_row(_ISO, [phone, pc], 1)
        assert first == second
        assert first is not None
        assert first["entry_id"] == "phone_verified:x"
        assert float(first["detail"]["completed_at"]) == local("17:12")

    def test_a_credit_with_no_time_writes_no_row(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            row = credit_row(_ISO, [{"workout_data": {"type": "phone_verified"}}], 0)
        assert row is None
        assert "no usable time" in caplog.text

    def test_a_rest_row_is_stamped_at_its_midnight(self) -> None:
        row = rest_row(_DAY, 5.0)
        assert row["detail"] == {
            "completed_at": str(local("00:00")),
            "declared_at": "5.0",
            "source": "rest_day",
        }


class TestAppend:
    def test_rows_are_signed_once(self, key: Path) -> None:
        del key
        row = credit_row(_ISO, [entry({"type": "phone_verified"})], 0)
        assert row is not None
        assert append_rows([row, dict(row)]) == 1
        assert append_rows([dict(row)]) == 0
        (stored,) = ledger()
        assert earned_time.verified(stored, KEY)

    def test_no_key_writes_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            assert append_rows([rest_row(_DAY, 1.0)]) == 0
        assert "NOT updated" in caplog.text
        assert not ledger_path().exists()

    @pytest.mark.usefixtures("key")
    def test_a_malformed_ledger_is_left_alone(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        ledger_path().parent.mkdir(parents=True)
        ledger_path().write_text("[]")
        with caplog.at_level(logging.WARNING):
            assert append_rows([rest_row(_DAY, 1.0)]) == 0
        assert existing_rows(ledger_path()) is None
        assert ledger_path().read_text() == "[]"

    def test_new_rows_dedups_within_and_against_the_ledger(self) -> None:
        a, b = rest_row(_DAY, 1.0), rest_row(date(2026, 10, 5), 1.0)
        assert new_rows([a, b, dict(b)], [a]) == [b]

    @pytest.mark.usefixtures("key")
    def test_every_log_credit_reaches_the_ledger(self, tmp_path: Path) -> None:
        """The log write chokepoint is the ledger's only writer for credits."""
        log = tmp_path / "log.json"
        write_signed_entry(
            log,
            _ISO,
            {"type": "manual_workout", "start_time": "17:00", "end_time": "18:00"},
        )
        write_signed_entry(log, _ISO, {"type": "relaxed_day_skip"})
        (row,) = ledger()
        assert row["detail"]["source"] == "manual"
        assert float(row["detail"]["completed_at"]) == local("18:00")


def test_the_ledger_lives_under_the_redirected_home() -> None:
    assert ledger_path().is_relative_to(_workout_ledger._earned.LEDGER_HOME)
