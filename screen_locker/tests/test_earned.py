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
from typing import TYPE_CHECKING

import earned_time
import pytest

from screen_locker import _constants, _earned
from screen_locker._earned import (
    earned_today,
    flat_earners,
    hhmm,
    ledger_file,
    registry,
    span,
)
from screen_locker.tests._earned_fixtures import (
    EXTRA,
    credit,
    register,
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


@pytest.fixture(name="key")
def key_fixture(tmp_path: Path) -> Iterator[Path]:
    """Install a valid HMAC signing key under the redirected key path."""
    with signing_key(tmp_path) as path:
        yield path


class TestHhmm:
    """Groups the ``hhmm`` renderer for minutes-after-midnight."""

    def test_whole_hours_are_zero_padded(self) -> None:
        """Whole hours render as zero-padded HH:00."""
        assert hhmm(0) == "00:00"
        assert hhmm(9 * 60) == "09:00"
        assert hhmm(21 * 60) == "21:00"

    def test_minutes_are_kept_exactly(self) -> None:
        """A 30-minute earner shows as :30, never floored to the hour."""
        assert hhmm(18 * 60 + 30) == "18:30"
        assert hhmm(5) == "00:05"

    def test_midnight_cap_is_24_00(self) -> None:
        """The 24h cap renders as 24:00 rather than wrapping to 00:00."""
        assert hhmm(24 * 60) == "24:00"


class TestSpan:
    """Groups the ``span`` duration renderer."""

    def test_whole_hours(self) -> None:
        """Whole-hour durations render as Nh with no minutes part."""
        assert span(0) == "0h"
        assert span(60) == "1h"
        assert span(120) == "2h"

    def test_minutes_only(self) -> None:
        """Durations under an hour render as Nm only."""
        assert span(30) == "30m"

    def test_hours_and_minutes_combine(self) -> None:
        """Mixed durations render as NhMMm with zero-padded minutes."""
        assert span(90) == "1h30m"
        assert span(125) == "2h05m"


class TestLedgerFile:
    """Groups how a ledger path is resolved and redirected in the suite."""

    @_LEDGERED
    def test_resolves_under_ledger_home(self, earner: earned_time.Earner) -> None:
        """A ledger file path is the earner's ledger name under LEDGER_HOME."""
        assert earner.ledger is not None
        assert ledger_file(earner) == _earned.LEDGER_HOME / earner.ledger

    def test_ledger_home_and_key_are_redirected_for_the_suite(
        self, tmp_path: Path
    ) -> None:
        """The suite points LEDGER_HOME and HMAC_KEY_FILE at tmp_path with no key present."""
        assert tmp_path / "ledger_home" == _earned.LEDGER_HOME
        assert tmp_path / "earned_hmac.key" == _earned.HMAC_KEY_FILE
        assert not _earned.HMAC_KEY_FILE.exists()

    def test_suite_never_sees_a_real_ledger(self) -> None:
        """No flat earner's ledger path exists during the suite, so real ledgers are never read."""
        assert not any(ledger_file(e).exists() for e in flat_earners())

    def test_earner_without_a_ledger_raises(self) -> None:
        """Asking for the ledger of an earner that has none raises ValueError."""
        bare = earned_time.Earner(
            name="bare", label="Bare", gaming_minutes=0, shutdown_minutes=0
        )
        with pytest.raises(ValueError, match="has no ledger"):
            ledger_file(bare)


class TestFlatEarners:
    """Groups which registry earners count as flat (ledger-read) earners."""

    def test_registry_order_without_the_counted_workout(self) -> None:
        """Flat earners keep registry order and exclude the counted workout earner."""
        flat = tuple(e for e in registry() if e.kind == "flat")
        assert flat_earners() == flat
        assert flat[:2] == (earned_time.LEETCODE, earned_time.READING)

    def test_a_newly_registered_earner_is_picked_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An earner added to the registry later appears among the flat earners."""
        register(monkeypatch, EXTRA)
        assert flat_earners()[-1] is EXTRA

    def test_a_flat_earner_without_a_ledger_is_left_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No ledger means no shared reader: its answer is the consumer's."""
        unledgered = earned_time.Earner(
            name="manual", label="manual", gaming_minutes=60, shutdown_minutes=60
        )
        register(monkeypatch, unledgered)
        assert unledgered not in flat_earners()

    def test_conftest_seeds_every_flat_earners_stamp(self) -> None:
        """So the live pass never reads a ledger (or the real key) by default."""
        seeded = json.loads(_constants.SHUTDOWN_BASE_FILE.read_text())
        for earner in flat_earners():
            assert f"{earner.name}_bonus_date" in seeded


@pytest.mark.usefixtures("leetcode_gate_off")
class TestEarnedToday:
    """Groups the ledger-backed 'did the earner earn today' answer."""

    @_LEDGERED
    def test_signed_credit_today_earns(
        self, key: Path, earner: earned_time.Earner
    ) -> None:
        """A validly signed credit dated today counts as earned."""
        write_ledger(earner, [credit(earner)])
        assert earned_today(earner) is True

    @_LEDGERED
    def test_now_is_passed_through(self, key: Path, earner: earned_time.Earner) -> None:
        """The ``now`` argument decides which day the credit is compared against."""
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
        """A ledger placed outside LEDGER_HOME is ignored and never counts as earned."""
        stray = tmp_path / "ledger.json"
        stray.write_text(json.dumps({"entries": [credit(earner)]}))
        assert earned_today(earner) is not True
