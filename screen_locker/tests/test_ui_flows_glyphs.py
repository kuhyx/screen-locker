"""The lock screens' glyphs (textgate): what each state paints, and what it logs.

Every sentence these screens used to paint now goes to the log at WARNING,
so each test checks both halves: the glyph on screen, the reason in the log.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _glyphs as g
from screen_locker import _ui_flows
from screen_locker._source_health import SourceFinding
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _labels(mock_tk: MagicMock) -> list[tuple[str, str]]:
    """(text, fg) of every Label, in call order."""
    return [
        (c.kwargs.get("text", ""), c.kwargs.get("fg", ""))
        for c in mock_tk.Label.call_args_list
    ]


def _warned(caplog: pytest.LogCaptureFixture) -> str:
    """Every WARNING message of the test, joined."""
    return "\n".join(r.getMessage() for r in caplog.records if r.levelname == "WARNING")


class TestRetryScreen:
    """``_show_retry_and_sick``: barbell-fail, status glyph, sync faults."""

    def test_too_short_paints_its_glyph_and_logs_the_reason(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A too-short session shows the short-clock glyph; its reason is logged."""
        monkeypatch.setattr(_ui_flows, "collect_source_findings", list)
        locker = create_locker(mock_tk, tmp_path)
        locker._handle_startup_phone_result("too_short", "only 12 min")
        labels = _labels(mock_tk)
        palette = locker._colors.palette
        assert (f"{g.LIFT} {g.FAIL}", palette.danger) in labels
        assert (g.SHORT, palette.warning) in labels
        assert "only 12 min" in _warned(caplog)
        assert not any("only 12 min" in text for text, _fg in labels)

    def test_no_status_paints_no_status_glyph(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Called without a status (the penalty timer's end), no status glyph."""
        monkeypatch.setattr(_ui_flows, "collect_source_findings", list)
        locker = create_locker(mock_tk, tmp_path)
        locker._show_retry_and_sick("phone gone")
        texts = [text for text, _fg in _labels(mock_tk)]
        assert not any(text in g.STATUS_GLYPH.values() for text in texts)
        assert g.FAIL not in texts

    def test_each_sync_finding_is_one_glyph_and_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two unreadable sources: two sync-fail glyphs; the prose goes to the log."""
        findings = [
            SourceFinding("firebase", "firebase unreadable", "401"),
            SourceFinding("mirror", "mirror stale", "9 days"),
        ]
        monkeypatch.setattr(_ui_flows, "collect_source_findings", lambda: findings)
        locker = create_locker(mock_tk, tmp_path)
        locker._show_retry_and_sick("x", status="stale")
        assert (
            f"{g.SYNC}{g.FAIL} " * 2,
            locker._colors.palette.warning,
        ) in _labels(mock_tk)
        assert "firebase unreadable" in _warned(caplog)
        assert "mirror stale" in _warned(caplog)


class TestAcceptedScreen:
    """``_paint_accepted``: source glyph + tick, wait dots, then unlock."""

    def test_verified_lift_paints_tick_and_schedules_unlock(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A verified lift paints barbell + tick in success, then the wait dots."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker.root, "after", MagicMock())
        locker._handle_startup_phone_result("verified", "Workout A")
        labels = _labels(mock_tk)
        assert (f"{g.LIFT} {g.OK}", locker._colors.palette.success) in labels
        assert g.WAIT in [text for text, _fg in labels]
        assert not any("Workout A" in text for text, _fg in labels)
        assert locker.workout_data["source"] == "Workout A"
        delay, callback = locker.root.after.call_args.args
        assert delay > 0
        assert callback == locker.unlock_screen

    def test_manual_save_paints_the_form_glyph(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """A saved manual entry paints form + tick, never the entry's source."""
        locker = create_locker(mock_tk, tmp_path)
        object.__setattr__(locker.root, "after", MagicMock())
        with patch.object(locker, "unlock_screen"):
            locker._on_manual_workout_saved({"source": "table tennis at Solec"})
        texts = [text for text, _fg in _labels(mock_tk)]
        assert f"{g.FORM} {g.OK}" in texts
        assert not any("Solec" in t for t in texts)


class TestGlyphHelpers:
    """The pure helpers in ``_glyphs``."""

    def test_dots_fills_up_to_total_and_keeps_the_real_count(self) -> None:
        """Dots never exceed the total; the numbers stay exact."""
        assert g.dots(2, 4) == "●●○○ 2/4"
        assert g.dots(6, 4) == "●●●● 6/4"
        assert g.dots(-1, 3) == "○○○ -1/3"

    def test_status_glyph_falls_back_to_fail(self) -> None:
        """A status with no glyph shows the plain fail mark."""
        assert g.status_glyph("too_short") == g.SHORT
        assert g.status_glyph("brand_new_status") == g.FAIL

    def test_entry_glyphs_maps_known_and_unknown_types(self) -> None:
        """Known types get their glyph; an unknown one shows a tick, in order."""
        assert g.entry_glyphs(("runnerup_verified", "mystery")) == f"{g.RUN} {g.OK}"
        assert g.entry_glyphs(()) == ""
