"""Tests for ``_earned``: an unreadable ledger or key fails closed to ``None``.

Companion to ``test_earned``; pins the cannot-check states and ``flat_answers``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import earned_time
import pytest

from screen_locker import _earned
from screen_locker._earned import earned_today, flat_answers, flat_earners, ledger_file
from screen_locker.tests._earned_fixtures import credit, signing_key, write_ledger

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_LEDGERED = pytest.mark.parametrize(
    "earner", [earned_time.LEETCODE, earned_time.READING], ids=lambda e: e.name
)


@pytest.fixture(name="key")
def key_fixture(tmp_path: Path) -> Iterator[Path]:
    """Install a valid HMAC signing key under the redirected key path."""
    with signing_key(tmp_path) as path:
        yield path


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
        """A whitespace-only key file is unreadable: the answer is None and a warning is logged."""
        write_ledger(earned_time.LEETCODE, [credit(earned_time.LEETCODE)])
        with signing_key(tmp_path, b"  \n"), caplog.at_level(logging.WARNING):
            assert earned_today(earned_time.LEETCODE) is None
        assert "is empty" in caplog.text

    def test_missing_leetcode_ledger_is_unknown(
        self, key: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A missing LeetCode ledger is None (cannot check) and warned, not a plain no."""
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
        """A ledger that is not valid JSON yields None and a warning, never False."""
        path = ledger_file(earner)
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        with caplog.at_level(logging.WARNING):
            assert earned_today(earner) is None
        assert "not valid JSON" in caplog.text


@pytest.mark.usefixtures("leetcode_gate_off")
class TestFlatAnswers:
    """Groups the per-earner answer map built by ``flat_answers``."""

    def test_every_flat_earner_answers_by_name(self, key: Path) -> None:
        """Every flat earner gets an entry by name, True only for the one with a credit today."""
        write_ledger(earned_time.LEETCODE, [credit(earned_time.LEETCODE)])
        nos = dict.fromkeys((e.name for e in flat_earners()), False)
        assert flat_answers() == {**nos, "leetcode": True}

    def test_an_unknown_answer_is_none_and_warned(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unreadable key makes every answer None and warns once per earner."""
        monkeypatch.setattr(_earned, "HMAC_KEY_FILE", tmp_path / "no.key")
        with caplog.at_level(logging.WARNING):
            assert flat_answers() == dict.fromkeys(e.name for e in flat_earners())
        for earner in flat_earners():
            assert f"{earner.label} state could not be checked" in caplog.text

    def test_a_no_is_not_warned(
        self, key: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A definite no (empty ledger) produces no could-not-be-checked warning."""
        write_ledger(earned_time.LEETCODE, [])
        with caplog.at_level(logging.WARNING):
            assert flat_answers() == dict.fromkeys(
                (e.name for e in flat_earners()), False
            )
        assert "could not be checked" not in caplog.text
