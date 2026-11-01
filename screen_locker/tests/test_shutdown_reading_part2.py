"""Live pass for the reading hour: applied once, never stamped on failure.

Split from test_shutdown_reading.py, which covers the base cut and the reset.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from screen_locker._day import today_str
from screen_locker._shutdown_base import base_minutes
from screen_locker.tests._earned_fixtures import answering
from screen_locker.tests.test_shutdown_reading import apply_reading_bonus_if_new

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _mixin(*, adjust_ok: bool = True) -> MagicMock:
    mixin = MagicMock()
    mixin._read_shutdown_config.return_value = (base_minutes(), base_minutes(), 300)
    mixin._write_shutdown_config.return_value = True
    mixin._adjust_shutdown_time_by.return_value = adjust_ok
    return mixin


@pytest.fixture(name="answers")
def answers_fixture() -> Iterator[tuple[dict[str, bool | None], MagicMock]]:
    """(answers, earned_today mock): every flat earner says no until set."""
    given: dict[str, bool | None] = {"leetcode": False, "reading": False}
    with answering(given) as mock:
        yield given, mock


class TestReadingLivePass:
    """The live pass adds the reading hour once, after the reset."""

    @pytest.mark.usefixtures("pre_ladder")
    def test_applies_once_and_stamps(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        """A reading credit is applied once and stamped, so the second pass does nothing."""
        answers[0]["reading"] = True
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"last_reset_date": today_str()}))
        mixin = _mixin()
        assert apply_reading_bonus_if_new(state, mixin) is True
        assert apply_reading_bonus_if_new(state, mixin) is False
        mixin._adjust_shutdown_time_by.assert_called_once_with(60, at=None)
        assert json.loads(state.read_text()) == {
            "last_reset_date": today_str(),
            "reading_bonus_date": today_str(),
        }

    def test_stamped_today_never_reads_the_ledger(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        """A day already stamped never queries the ledger again."""
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"reading_bonus_date": today_str()}))
        assert apply_reading_bonus_if_new(state, _mixin()) is False
        answers[1].assert_not_called()

    def test_no_reading_no_write(
        self, tmp_path: Path, answers: tuple[dict[str, bool | None], MagicMock]
    ) -> None:
        """With no reading credit the live pass writes nothing."""
        mixin = _mixin()
        assert apply_reading_bonus_if_new(tmp_path / "state.json", mixin) is False
        mixin._adjust_shutdown_time_by.assert_not_called()

    def test_failed_write_leaves_no_stamp_and_warns(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A stamp without a write would silently forfeit the hour for the day."""
        answers[0]["reading"] = True
        state = tmp_path / "state.json"
        mixin = _mixin(adjust_ok=False)
        with caplog.at_level("WARNING"):
            assert apply_reading_bonus_if_new(state, mixin) is False
        assert "reading bonus: failed to write" in caplog.text
        assert not state.exists()

    def test_cannot_check_warns_and_leaves_no_stamp(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unknown is not "no": logged, no hour, and re-asked on the next tick."""
        answers[0]["reading"] = None
        state = tmp_path / "state.json"
        mixin = _mixin()
        with caplog.at_level("WARNING"):
            assert apply_reading_bonus_if_new(state, mixin) is False
        assert "reading state could not be checked" in caplog.text
        mixin._adjust_shutdown_time_by.assert_not_called()
        assert not state.exists()

    @pytest.mark.usefixtures("pre_ladder")
    def test_applied_hour_is_logged(
        self,
        tmp_path: Path,
        answers: tuple[dict[str, bool | None], MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Applying the reading hour logs it."""
        answers[0]["reading"] = True
        with caplog.at_level("INFO"):
            assert apply_reading_bonus_if_new(tmp_path / "state.json", _mixin())
        assert "reading bonus: +1h shutdown time today." in caplog.text
