"""Tests for ``_rest_day`` and its CLI: declared ahead, two a week, signed."""

from __future__ import annotations

from datetime import date, datetime, time
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

import earned_time
import pytest

from screen_locker import _earned, _rest_day
from screen_locker._rest_day import declare, is_rest_day, rest_day_declarations
from screen_locker._rest_day_cli import run_declare_rest_day
from screen_locker._workout_ledger import ledger_path
from screen_locker.tests._earned_fixtures import KEY, signing_key

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_EVE = datetime.combine(date(2026, 10, 9), time(18, 55)).astimezone()
_SAT, _SUN, _MON = date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)


@pytest.fixture
def key(tmp_path: Path) -> Iterator[Path]:
    with signing_key(tmp_path) as path:
        yield path


def rows() -> list[dict[str, object]]:
    return json.loads(_rest_day.REST_DAY_FILE.read_text())["entries"]


def write(entries: object) -> None:
    _rest_day.REST_DAY_FILE.write_text(json.dumps({"entries": entries}))


@pytest.mark.usefixtures("key")
class TestDeclare:
    def test_a_future_day_is_signed_and_mirrored_to_the_ledger(self) -> None:
        result = declare(_SAT, now=_EVE)
        assert result.ok
        assert result.reason == "2026-10-10 is a rest day (1 left in ISO week 41)"
        (row,) = rows()
        assert earned_time.verified(row, KEY)
        assert row["declared_on"] == "2026-10-09"
        (credit,) = json.loads(ledger_path().read_text())["entries"]
        assert credit["entry_id"] == "rest:2026-10-10"
        assert credit["detail"]["source"] == "rest_day"
        assert float(credit["detail"]["declared_at"]) == _EVE.timestamp()
        midnight = datetime.combine(_SAT, time.min).astimezone().timestamp()
        assert float(credit["detail"]["completed_at"]) == midnight
        assert is_rest_day(_SAT)

    @pytest.mark.parametrize("day", [date(2026, 10, 9), date(2026, 10, 1)])
    def test_today_and_the_past_are_refused(self, day: date) -> None:
        result = declare(day, now=_EVE)
        assert not result.ok
        assert "not in the future" in result.reason
        assert not _rest_day.REST_DAY_FILE.exists()

    def test_two_per_iso_week_then_refused(self) -> None:
        assert declare(_SAT, now=_EVE).ok
        assert declare(_SUN, now=_EVE).reason.endswith("(0 left in ISO week 41)")
        assert declare(_SUN, now=_EVE).reason == "2026-10-11 is already a rest day"
        third = declare(date(2026, 10, 8 + 1), now=datetime(2026, 10, 8).astimezone())
        assert not third.ok
        assert third.reason == "ISO week 41 already has 2 rest days"
        assert declare(_MON, now=_EVE).ok  # the next week has its own two

    def test_an_unreadable_file_refuses(self, caplog: pytest.LogCaptureFixture) -> None:
        _rest_day.REST_DAY_FILE.write_text("{not json")
        with caplog.at_level(logging.WARNING):
            result = declare(_SAT, now=_EVE)
        assert not result.ok
        assert result.reason == "rest-day file or signing key unreadable"
        assert "unreadable" in caplog.text

    def test_a_failed_write_says_so(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            patch.object(
                type(_rest_day.REST_DAY_FILE), "write_text", side_effect=OSError("ro")
            ),
            caplog.at_level(logging.WARNING),
        ):
            result = declare(_SAT, now=_EVE)
        assert not result.ok
        assert "could not write" in result.reason


class TestReading:
    def test_no_key_counts_nothing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            assert rest_day_declarations() == {}
        assert "signing key" in caplog.text
        with signing_key(tmp_path, b"  "):
            assert rest_day_declarations() == {}

    @pytest.mark.usefixtures("key")
    def test_a_hand_edited_row_is_ignored(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        declare(_SAT, now=_EVE)
        edited = rows()
        edited[0]["day"] = "2026-10-14"
        write(edited)
        with caplog.at_level(logging.WARNING):
            assert rest_day_declarations() == {}
        assert "fails its signature" in caplog.text

    @pytest.mark.usefixtures("key")
    def test_a_signed_same_day_row_is_not_ahead(self) -> None:
        """A row from any other route still has to be declared ahead."""
        body = {
            "kind": "rest_day",
            "day": "2026-10-10",
            "declared_on": "2026-10-10",
            "declared_at": 1.0,
        }
        write([{**body, "hmac": earned_time.entry_signature(body, KEY)}])
        assert rest_day_declarations() == {}

    @pytest.mark.usefixtures("key")
    def test_malformed_and_foreign_rows_are_ignored(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        body = {
            "kind": "rest_day",
            "day": "soon",
            "declared_on": "2026-10-09",
            "declared_at": 1.0,
        }
        write(
            [
                "x",
                {"kind": "other"},
                {**body, "hmac": earned_time.entry_signature(body, KEY)},
            ]
        )
        with caplog.at_level(logging.WARNING):
            assert rest_day_declarations() == {}
        assert "malformed" in caplog.text

    @pytest.mark.usefixtures("key")
    def test_a_file_without_entries_counts_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        _rest_day.REST_DAY_FILE.write_text("[]")
        with caplog.at_level(logging.WARNING):
            assert rest_day_declarations() == {}
        assert "no entries array" in caplog.text

    @pytest.mark.usefixtures("key")
    def test_the_cap_holds_on_read(self) -> None:
        """Three signed rows in a week: the two declared first count."""

        def row(day: str, at: float) -> dict[str, object]:
            body = {
                "kind": "rest_day",
                "day": day,
                "declared_on": "2026-10-01",
                "declared_at": at,
            }
            return {**body, "hmac": earned_time.entry_signature(body, KEY)}

        write([row("2026-10-07", 3.0), row("2026-10-05", 1.0), row("2026-10-06", 2.0)])
        assert set(rest_day_declarations()) == {date(2026, 10, 5), date(2026, 10, 6)}


@pytest.mark.usefixtures("key")
class TestCli:
    def _run(self, *argv: str, offset: float | None = 0.0) -> int:
        with (
            patch("screen_locker._rest_day_cli._query_ntp_offset", return_value=offset),
            patch("screen_locker._rest_day_cli.today_str", return_value="2026-10-09"),
            patch("screen_locker._rest_day.datetime") as clock,
        ):
            clock.now.return_value = _EVE
            return run_declare_rest_day(list(argv))

    def test_declare_tomorrow(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run("tomorrow") == 0
        assert "2026-10-10 is a rest day" in capsys.readouterr().out

    def test_a_date_and_then_the_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run("2026-10-11") == 0
        assert self._run("--list") == 0
        assert capsys.readouterr().out.splitlines()[-1] == "2026-10-11"

    def test_an_empty_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run() == 0
        assert capsys.readouterr().out.strip() == "no rest days declared"

    def test_a_bad_date(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run("someday") == 2
        assert capsys.readouterr().out.startswith("error:")

    def test_no_ntp_refuses(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run("tomorrow", offset=None) == 1
        assert "cannot be confirmed" in capsys.readouterr().out

    def test_a_skewed_clock_refuses(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run("tomorrow", offset=86400.0) == 1
        assert "off by 86400s" in capsys.readouterr().out

    def test_today_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run("2026-10-09") == 1
        assert "refused: 2026-10-09 is not in the future" in capsys.readouterr().out


def test_the_key_binding_is_the_one_earned_reads() -> None:
    """The suite redirects ``_earned.HMAC_KEY_FILE``; rest days must follow it."""
    assert not _earned.HMAC_KEY_FILE.exists()
