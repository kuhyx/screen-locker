"""Tests for ``_earned``: where screen-locker reads each earner's ledger, and how.

Which rows count -- forged rows, yesterday's solve, an unparsable stamp -- is
``earned_time``'s rule and is tested there. Pinned here is screen-locker's
side of it: the ledger lives under ``LEDGER_HOME``, the key is
``HMAC_KEY_FILE``, an unreadable one fails closed to ``None`` and is logged,
and the schedule's times are shown exactly (``hhmm`` / ``span``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING

import earned_time
import pytest

from screen_locker import _constants, _earned
from screen_locker._earned import (
    earned_today,
    flat_answers,
    flat_earners,
    hhmm,
    ledger_file,
    span,
)
from screen_locker.tests._earned_fixtures import (
    EXTRA,
    credit,
    signing_key,
    write_ledger,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_NOW = datetime(2026, 10, 2, 14, 0).astimezone()
_LEDGERED = pytest.mark.parametrize(
    "earner", [earned_time.LEETCODE, earned_time.READING], ids=lambda e: e.name
)


@pytest.fixture
def key(tmp_path: Path) -> Iterator[Path]:
    with signing_key(tmp_path) as path:
        yield path


class TestHhmm:
    def test_whole_hours_are_zero_padded(self) -> None:
        assert hhmm(0) == "00:00"
        assert hhmm(9 * 60) == "09:00"
        assert hhmm(21 * 60) == "21:00"

    def test_minutes_are_kept_exactly(self) -> None:
        """A 30-minute earner shows as :30, never floored to the hour."""
        assert hhmm(18 * 60 + 30) == "18:30"
        assert hhmm(5) == "00:05"

    def test_midnight_cap_is_24_00(self) -> None:
        assert hhmm(24 * 60) == "24:00"


class TestSpan:
    def test_whole_hours(self) -> None:
        assert span(0) == "0h"
        assert span(60) == "1h"
        assert span(120) == "2h"

    def test_minutes_only(self) -> None:
        assert span(30) == "30m"

    def test_hours_and_minutes_combine(self) -> None:
        assert span(90) == "1h30m"
        assert span(125) == "2h05m"


class TestLedgerFile:
    @_LEDGERED
    def test_resolves_under_ledger_home(self, earner: earned_time.Earner) -> None:
        assert earner.ledger is not None
        assert ledger_file(earner) == _earned.LEDGER_HOME / earner.ledger

    def test_ledger_home_and_key_are_redirected_for_the_suite(
        self, tmp_path: Path
    ) -> None:
        assert tmp_path / "ledger_home" == _earned.LEDGER_HOME
        assert tmp_path / "earned_hmac.key" == _earned.HMAC_KEY_FILE
        assert not _earned.HMAC_KEY_FILE.exists()

    def test_suite_never_sees_a_real_ledger(self) -> None:
        assert not any(ledger_file(e).exists() for e in flat_earners())

    def test_earner_without_a_ledger_raises(self) -> None:
        with pytest.raises(ValueError, match="has no ledger"):
            ledger_file(earned_time.WORKOUT)


class TestFlatEarners:
    def test_registry_order_without_the_counted_workout(self) -> None:
        flat = tuple(e for e in earned_time.EARNERS if e.kind == "flat")
        assert flat_earners() == flat
        assert flat[:3] == (earned_time.LEETCODE, earned_time.READING, earned_time.ANKI)

    def test_a_newly_registered_earner_is_picked_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(earned_time, "EARNERS", (*earned_time.EARNERS, EXTRA))
        assert flat_earners()[-1] is EXTRA

    def test_a_flat_earner_without_a_ledger_is_left_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No ledger means no shared reader: its answer is the consumer's."""
        unledgered = earned_time.Earner(
            name="manual", label="manual", gaming_minutes=60, shutdown_minutes=60
        )
        monkeypatch.setattr(earned_time, "EARNERS", (*earned_time.EARNERS, unledgered))
        assert unledgered not in flat_earners()

    def test_conftest_seeds_every_flat_earners_stamp(self) -> None:
        """So the live pass never reads a ledger (or the real key) by default."""
        seeded = json.loads(_constants.SHUTDOWN_BASE_FILE.read_text())
        for earner in flat_earners():
            assert f"{earner.name}_bonus_date" in seeded


class TestEarnedToday:
    @_LEDGERED
    def test_signed_credit_today_earns(
        self, key: Path, earner: earned_time.Earner
    ) -> None:
        write_ledger(earner, [credit(earner)])
        assert earned_today(earner) is True

    @_LEDGERED
    def test_now_is_passed_through(self, key: Path, earner: earned_time.Earner) -> None:
        write_ledger(earner, [credit(earner, _NOW - timedelta(hours=1))])
        assert earned_today(earner, now=_NOW) is True
        assert earned_today(earner, now=_NOW - timedelta(hours=2)) is False
        assert earned_today(earner, now=_NOW + timedelta(days=1)) is False

    @_LEDGERED
    def test_rows_are_verified_against_hmac_key_file(
        self, tmp_path: Path, earner: earned_time.Earner
    ) -> None:
        """Signed with another key than the one on disk: a forgery, no time."""
        write_ledger(earner, [credit(earner)])
        with signing_key(tmp_path, b"another-key"):
            assert earned_today(earner) is False

    @_LEDGERED
    def test_a_ledger_outside_ledger_home_is_never_read(
        self, tmp_path: Path, key: Path, earner: earned_time.Earner
    ) -> None:
        stray = tmp_path / "ledger.json"
        stray.write_text(json.dumps({"entries": [credit(earner)]}))
        assert earned_today(earner) is not True


class TestCannotCheck:
    """Every unreadable state is None -- never a confident False -- and logged."""

    @_LEDGERED
    def test_missing_key(
        self,
        tmp_path: Path,
        earner: earned_time.Earner,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The key is checked first: without it even "no ledger" is unknown."""
        monkeypatch.setattr(_earned, "HMAC_KEY_FILE", tmp_path / "no.key")
        with caplog.at_level(logging.WARNING):
            assert earned_today(earner) is None
        assert "Cannot read the integrity key" in caplog.text

    def test_empty_key(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        write_ledger(earned_time.LEETCODE, [credit(earned_time.LEETCODE)])
        with signing_key(tmp_path, b"  \n"), caplog.at_level(logging.WARNING):
            assert earned_today(earned_time.LEETCODE) is None
        assert "is empty" in caplog.text

    def test_missing_leetcode_ledger_is_unknown(
        self, key: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            assert earned_today(earned_time.LEETCODE) is None
        assert "Cannot read the LeetCode ledger" in caplog.text

    def test_missing_reading_ledger_is_a_plain_no(self, key: Path) -> None:
        """book-guard never ran: no reading, but no fault either."""
        assert earned_today(earned_time.READING) is False

    @_LEDGERED
    def test_corrupt_ledger(
        self,
        key: Path,
        earner: earned_time.Earner,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        path = ledger_file(earner)
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        with caplog.at_level(logging.WARNING):
            assert earned_today(earner) is None
        assert "not valid JSON" in caplog.text


class TestFlatAnswers:
    def test_every_flat_earner_answers_by_name(self, key: Path) -> None:
        write_ledger(earned_time.LEETCODE, [credit(earned_time.LEETCODE)])
        nos = dict.fromkeys((e.name for e in flat_earners()), False)
        assert flat_answers() == {**nos, "leetcode": True}

    def test_an_unknown_answer_is_none_and_warned(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(_earned, "HMAC_KEY_FILE", tmp_path / "no.key")
        with caplog.at_level(logging.WARNING):
            assert flat_answers() == dict.fromkeys(e.name for e in flat_earners())
        for earner in flat_earners():
            assert f"{earner.label} state could not be checked" in caplog.text

    def test_a_no_is_not_warned(
        self, key: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        write_ledger(earned_time.LEETCODE, [])
        with caplog.at_level(logging.WARNING):
            assert flat_answers() == dict.fromkeys(
                (e.name for e in flat_earners()), False
            )
        assert "could not be checked" not in caplog.text
