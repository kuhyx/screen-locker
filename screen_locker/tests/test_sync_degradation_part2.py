"""The DECISION line must name a backend it could not read.

Split from ``test_sync_degradation.py`` to keep both files under the 250-line
cap; same subject, which is that "could not check" and "did not train" are
different claims and only one of them justifies locking the screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from screen_locker import _startup_checks, _sync_client

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestDecisionLineNamesTheDeadBackend:
    """A degraded read must be named on the DECISION line itself.

    A warning logged 90 seconds earlier is not enough: the line that says
    ``weekly=0/5`` has to say whether that zero was measured or merely
    unreadable, or a reader tracing the journal draws the wrong conclusion
    about the user (see this module's docstring).
    """

    def _locker(self, tmp_path: Path) -> object:
        """A StartupChecksMixin with __init__ bypassed, as the CLI builds it."""
        locker = object.__new__(_startup_checks.StartupChecksMixin)
        locker.log_file = tmp_path / "log.json"
        # Stubbed: the ladder annotation is its own concern, tested elsewhere.
        locker._other_conditions = lambda _reason: {}
        return locker

    def test_annotates_the_decision_with_the_unreadable_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The dead backend's name reaches the recorded decision."""
        recorded: list[object] = []
        monkeypatch.setattr(
            _startup_checks,
            "degraded_sources",
            lambda: (_sync_client.DegradedSource("firebase", "HTTP 401"),),
        )
        monkeypatch.setattr(_startup_checks, "count_weekly_workouts", lambda _: 0)
        monkeypatch.setattr(
            _startup_checks, "record_decision", lambda d, **_: recorded.append(d)
        )

        self._locker(tmp_path)._record_decision(
            locked=False, reason="weekly_minimum_met", detail=""
        )

        assert recorded[0].extra["unreadable_sources"] == "firebase"

    def test_healthy_sources_add_no_annotation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With every backend answering, the line stays unannotated."""
        recorded: list[object] = []
        monkeypatch.setattr(_startup_checks, "degraded_sources", tuple)
        monkeypatch.setattr(_startup_checks, "count_weekly_workouts", lambda _: 0)
        monkeypatch.setattr(
            _startup_checks, "record_decision", lambda d, **_: recorded.append(d)
        )

        self._locker(tmp_path)._record_decision(
            locked=False, reason="weekly_minimum_met", detail=""
        )

        assert "unreadable_sources" not in recorded[0].extra
