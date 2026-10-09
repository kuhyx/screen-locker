"""Tests for ``--backfill-workout-ledger``: idempotent, per source, range-aware."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from screen_locker._rest_day import declare
from screen_locker._workout_ledger import ledger_path
from screen_locker._workout_ledger_cli import backfill_rows, run_backfill
from screen_locker.tests._earned_fixtures import signing_key

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_DAY = date(2026, 10, 4)
_ISO = _DAY.isoformat()


@pytest.fixture
def key(tmp_path: Path) -> Iterator[Path]:
    with signing_key(tmp_path) as path:
        yield path


def entry(data: dict[str, Any]) -> dict[str, Any]:
    return {"timestamp": "2026-10-04T20:00:00+00:00", "workout_data": data}


def ledger() -> list[dict[str, Any]]:
    return json.loads(ledger_path().read_text())["entries"]


@pytest.mark.usefixtures("key")
class TestBackfill:
    def _log(self, tmp_path: Path) -> Path:
        log = tmp_path / "log.json"
        log.write_text(
            json.dumps(
                {
                    _ISO: [
                        entry({"type": "phone_verified"}),
                        entry({"type": "relaxed_day_skip"}),
                    ],
                    "2026-10-05": [
                        entry({"type": "runnerup_verified", "completed_at": 9.0})
                    ],
                }
            )
        )
        return log

    def test_rows_for_a_range_and_its_rest_days(self, tmp_path: Path) -> None:
        with patch("screen_locker._rest_day.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 1).astimezone()
            assert declare(date(2026, 10, 6)).ok
        ledger_path().unlink()  # the declaration mirrored it; backfill must too
        rows = backfill_rows(self._log(tmp_path), _DAY, date(2026, 10, 6))
        assert [r["detail"]["source"] for r in rows] == [
            "stronglifts",
            "runnerup_tcx",
            "rest_day",
        ]

    def test_dry_run_prints_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ["--dry-run", "--from", _ISO, "--to", "2026-10-05"]
        assert run_backfill(self._log(tmp_path), argv) == 0
        out = capsys.readouterr().out
        assert "(missing)" in out
        assert "per source: {'runnerup_tcx': 1, 'stronglifts': 1}" in out
        assert not ledger_path().exists()

    def test_a_real_run_is_idempotent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        log = self._log(tmp_path)
        assert run_backfill(log, ["--from", _ISO, "--to", "2026-10-05"]) == 0
        assert run_backfill(log, ["--from", _ISO, "--to", "2026-10-05"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[0].startswith("2 new row(s)")
        assert out[1].startswith("0 new row(s)")
        assert run_backfill(log, ["--dry-run"]) == 0
        assert "(present)" in capsys.readouterr().out

    def test_default_is_today(self, tmp_path: Path) -> None:
        with patch("screen_locker._workout_ledger_cli.today_str", return_value=_ISO):
            assert run_backfill(self._log(tmp_path), []) == 0
        assert len(ledger()) == 1
