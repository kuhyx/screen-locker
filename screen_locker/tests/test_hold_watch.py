"""An open workout window closes when a hold starts; the status page names it."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from screen_locker._compliance_state import explain_lock_decision
from screen_locker._hold import watch_for_hold
from screen_locker.tests._hold_fakes import fake_holds_module
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path


class TestWatchForHold:
    """An already-open window closes within one poll of a hold starting."""

    def test_arms_a_poll_no_longer_than_thirty_seconds(self) -> None:
        """The first check is scheduled on the Tk loop, <= 30 s out."""
        root, close = MagicMock(), MagicMock()
        watch_for_hold(root, close)
        delay, _tick = root.after.call_args.args
        assert 0 < delay <= 30_000
        close.assert_not_called()

    def test_no_hold_rearms_and_does_not_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without a hold the tick only schedules the next one."""
        monkeypatch.setitem(sys.modules, "holds", fake_holds_module(covers=False))
        root, close = MagicMock(), MagicMock()
        watch_for_hold(root, close)
        root.after.call_args.args[1]()
        assert root.after.call_count == 2
        close.assert_not_called()

    def test_hold_closes_the_window_and_stops_polling(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A hold that starts mid-window closes it, once, and says so."""
        monkeypatch.setitem(sys.modules, "holds", fake_holds_module(covers=True))
        root, close = MagicMock(), MagicMock()
        watch_for_hold(root, close)
        with caplog.at_level(logging.WARNING, logger="screen_locker._hold"):
            root.after.call_args.args[1]()
        close.assert_called_once_with()
        assert root.after.call_count == 1
        assert "hold" in caplog.text

    def test_construction_arms_the_watch(
        self, mock_tk: MagicMock, tmp_path: Path
    ) -> None:
        """A built locker has the watch armed on its own root and ``close``."""
        with patch("screen_locker.screen_lock.watch_for_hold") as watch:
            locker = create_locker(mock_tk, tmp_path)
        watch.assert_called_once_with(locker.root, locker.close)


class TestStatusMirror:
    """The status explainer names the hold instead of ``would_lock``."""

    def _explain(self, tmp_path: Path, *, covers: bool) -> object:
        sys.modules["holds"] = fake_holds_module(covers=covers)
        return explain_lock_decision(
            log_file=tmp_path / "log.json",
            early_bird_pending_file=tmp_path / "early_bird_pending.json",
            weekly_minimum_met=False,
            relaxed_day=False,
        )

    @pytest.fixture(autouse=True)
    def _restore_holds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Let the test's own ``sys.modules['holds']`` be undone afterwards."""
        monkeypatch.setitem(sys.modules, "holds", sys.modules.get("holds"))

    def test_an_active_hold_is_the_terminal_stage(self, tmp_path: Path) -> None:
        """The explanation stops at test_hold_active without firing."""
        result = self._explain(tmp_path, covers=True)
        assert result.stage == "test_hold_active"
        assert result.fired is False

    def test_without_it_the_chain_still_would_lock(self, tmp_path: Path) -> None:
        """No hold: the explanation still reaches would_lock."""
        assert self._explain(tmp_path, covers=False).stage == "would_lock"

    def test_other_conditions_name_the_hold(
        self, mock_tk: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A decision made for another reason still reports the hold as also=."""
        locker = create_locker(mock_tk, tmp_path)
        monkeypatch.setitem(sys.modules, "holds", fake_holds_module(covers=True))
        assert "test_hold_active" in str(locker._other_conditions("enforced"))
