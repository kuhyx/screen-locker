"""A short verified RunnerUp day leaves a signed "progress" row in the ledger.

The row is inert today (its reader ships in a later ``earned_time``): these
tests pin that it is written, signed, and that nothing else moves.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _progress_row
from screen_locker._log_mixin import write_signed_entry
from screen_locker._workout_ledger import ledger_path
from screen_locker.tests._activity_helpers import DAY, Verifier, drop, tcx, verify
from screen_locker.tests._earned_fixtures import KEY, signing_key

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_PROGRESS_KEYS = {"kind", "entry_id", "day", "amount", "detail", "hmac"}


@pytest.fixture(name="verifier")
def verifier_fixture(tmp_path: Path) -> Verifier:
    """A Verifier reading a temporary drop directory."""
    drop_dir = tmp_path / "drop"
    drop_dir.mkdir()
    return Verifier(drop_dir)


@pytest.fixture(autouse=True, name="key")
def key_fixture(tmp_path: Path) -> Iterator[Path]:
    """A signing key, so the ledger writes (the suite default has none)."""
    with signing_key(tmp_path) as path:
        yield path


def rows() -> list[dict[str, Any]]:
    """The ledger's rows, or none when it was never written."""
    if not ledger_path().exists():
        return []
    return json.loads(ledger_path().read_text())["entries"]


def run(verifier: Verifier, start: str, *, moving_min: float, metres: float) -> None:
    """Drop one export for the test day."""
    drop(
        verifier.folder,
        start.replace(":", "-") + "-00",
        "_Running",
        tcx("Running", start, moving_min=moving_min, metres=metres),
    )


class TestWritten:
    """What a too-short verified day writes."""

    def test_1750_m_against_3500_m_writes_the_distance_form(
        self, verifier: Verifier
    ) -> None:
        """Half the distance bar: ``progress:<day>:1750:3500``, signed and valid."""
        run(verifier, "07:00", moving_min=5, metres=1750)
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"
        (row,) = rows()
        assert set(row) == _PROGRESS_KEYS
        assert row["kind"] == "progress"
        assert row["entry_id"] == f"progress:{DAY}:1750:3500"
        assert row["day"] == DAY
        assert row["amount"] is not None
        assert not row["amount"]
        assert row["detail"] == {
            "source": "workout",
            "for_day": DAY,
            "done": "1750",
            "target": "3500",
        }
        assert earned_time.verified(row, KEY)

    def test_20_min_moving_with_little_distance_writes_the_seconds_form(
        self, verifier: Verifier
    ) -> None:
        """Time leads: done is the moving seconds, target the time bar in seconds."""
        run(verifier, "07:00", moving_min=20, metres=1500)
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"
        (row,) = rows()
        assert row["entry_id"] == f"progress:{DAY}:1200:1800"
        assert row["detail"]["done"] == "1200"
        assert row["detail"]["target"] == "1800"
        assert earned_time.verified(row, KEY)

    def test_two_short_runs_sum(self, verifier: Verifier) -> None:
        """900 m + 850 m in one day is one progress of 1750 m."""
        run(verifier, "07:00", moving_min=3, metres=900)
        run(verifier, "18:00", moving_min=3, metres=850)
        result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"
        (row,) = rows()
        assert row["entry_id"] == f"progress:{DAY}:1750:3500"

    def test_a_second_short_run_writes_a_new_row_and_never_the_same_id_twice(
        self, verifier: Verifier
    ) -> None:
        """More done is a new id; the same done again writes nothing."""
        run(verifier, "07:00", moving_min=3, metres=900)
        verify(verifier)
        verify(verifier)
        assert [r["entry_id"] for r in rows()] == [f"progress:{DAY}:900:3500"]
        run(verifier, "18:00", moving_min=3, metres=850)
        verify(verifier)
        verify(verifier)
        assert [r["entry_id"] for r in rows()] == [
            f"progress:{DAY}:900:3500",
            f"progress:{DAY}:1750:3500",
        ]

    def test_the_weekly_scan_writes_it_for_its_own_day(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        """The backfill path judges the same too-short day and files it under it."""
        run(verifier, "07:00", moving_min=5, metres=1750)
        assert verifier._try_fill_runnerup_for_date(DAY, tmp_path / "log.json") is False
        (row,) = rows()
        assert row["entry_id"] == f"progress:{DAY}:1750:3500"


class TestNotWritten:
    """The days that must leave no progress row."""

    def test_a_qualifying_day_writes_the_credit_and_no_progress_row(
        self, verifier: Verifier, tmp_path: Path
    ) -> None:
        """A day over the bar credits as before; the ledger holds the credit only."""
        run(verifier, "07:00", moving_min=30, metres=4000)
        result = verify(verifier)
        assert result is not None
        assert result[0] == "verified"
        assert not rows()
        log = tmp_path / "log.json"
        assert verifier._try_fill_runnerup_for_date(DAY, log) is True
        assert [r["kind"] for r in rows()] == ["credit"]

    def test_manual_and_stronglifts_days_write_no_progress_row(
        self, tmp_path: Path
    ) -> None:
        """Only verified RunnerUp data has a "too short"; the others are all-or-nothing."""
        log = tmp_path / "log.json"
        write_signed_entry(
            log,
            DAY,
            {"type": "manual_workout", "start_time": "17:00", "end_time": "18:00"},
        )
        write_signed_entry(log, DAY, {"type": "phone_verified", "workout_id": "p:1"})
        assert rows()
        assert {r["kind"] for r in rows()} == {"credit"}

    def test_an_unreadable_tcx_is_could_not_check_and_writes_nothing(
        self, verifier: Verifier
    ) -> None:
        """Broken XML is "not_verified": no row, no guess."""
        drop(verifier.folder, "07-00-00", "_Running", "<not-xml")
        result = verify(verifier)
        assert result is not None
        assert result[0] == "not_verified"
        assert not rows()

    def test_the_root_db_path_is_not_verified_data_and_writes_nothing(
        self, verifier: Verifier
    ) -> None:
        """The rooted-DB fallback judges a dict, never a TCX: no row."""
        row = {"sport": 0, "duration_seconds": 10 * 60, "distance_m": 2000.0}
        assert verifier._validate_runnerup_data(row)[0] == "too_short"
        assert not rows()


class TestFailureModes:
    """A row that cannot be written never changes the verdict."""

    def test_no_signing_key_keeps_the_verdict_and_warns(
        self,
        verifier: Verifier,
        key: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No key: the same too_short, one warning, no ledger."""
        key.unlink()
        run(verifier, "07:00", moving_min=5, metres=1750)
        with caplog.at_level(logging.WARNING):
            result = verify(verifier)
        assert result is not None
        assert result[0] == "too_short"
        assert not rows()
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_an_unexpected_writer_error_keeps_the_verdict_and_logs(
        self, verifier: Verifier, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Whatever the writer raises, the verdict is untouched and the error logged."""
        run(verifier, "07:00", moving_min=5, metres=1750)
        before = verify(verifier)
        with (
            patch.object(_progress_row, "append_rows", side_effect=RuntimeError("x")),
            caplog.at_level(logging.WARNING),
        ):
            after = verify(verifier)
        assert after == before
        assert "progress row" in caplog.text


class TestNothingShowsTheBars:
    """No message, log line or print carries a threshold."""

    def test_no_threshold_in_logs_or_output(
        self,
        verifier: Verifier,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The bars live only inside the signed row."""
        run(verifier, "07:00", moving_min=5, metres=1750)
        with caplog.at_level(logging.DEBUG):
            verify(verifier)
        logged = "\n".join(r.getMessage() for r in caplog.records)
        seen = logged.replace(str(tmp_path), "") + capsys.readouterr().out
        for number in ("3500", "1800", "1500", "3325", "3.5", "25"):
            assert number not in seen
