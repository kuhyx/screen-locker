"""A degraded workout source must never be reported as "no workout".

Regression tests for 2026-06-12 and 2026-08-24, when a completed ~2h workout
sat in Firebase while the PC locked the screen anyway. The PC's Firebase
credential no longer authenticated, so ``remote_client`` degraded to the
GitHub mirror -- which the phone had stopped writing to on 2026-08-15. The
pull then returned zero records and the lock chain read that as "you did not
train today" rather than "I could not read the place your workouts live".

The distinction is the whole point. "No workout" is a statement about the
user; "could not check" is a statement about the machine, and only one of
them justifies taking the screen away.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from crdt_sync import FirebaseAuthError

from screen_locker import _sync_client, _workout_sync
from screen_locker._compliance_state import explain_lock_decision
from screen_locker._sick_tracker import SickHistory
from screen_locker.tests._workout_sync_fixtures import _firebase_config

if TYPE_CHECKING:
    import pytest


class TestUnreadableSourceIsNotNoWorkout:
    """The 2026-08-24 lockout, at the layer that actually took the screen.

    With Firebase unreadable the PC had NO information about today. It
    reported "No workout logged for today yet" and locked. These assertions
    fail on the old code, which is the point: they encode the difference
    between an answer and a failure to ask.
    """

    def _files(self, tmp_path: Path) -> dict[str, Path]:
        return {
            "log_file": tmp_path / "log.json",
            "scheduled_skips_file": tmp_path / "scheduled_skips.json",
            "early_bird_pending_file": tmp_path / "early_bird_pending.json",
        }

    def test_lock_reports_unreadable_source_not_absent_workout(
        self, tmp_path: Path
    ) -> None:
        """An empty log plus a dead backend must not read as "you did nothing"."""
        result = explain_lock_decision(
            **self._files(tmp_path),
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
            degraded_sources=(_sync_client.DegradedSource("firebase", "HTTP 400"),),
        )

        assert result.sources_degraded is True
        assert "firebase" in result.reason.lower()

    def test_healthy_sources_keep_the_plain_verdict(self, tmp_path: Path) -> None:
        """With every backend answering, an empty log really does mean none."""
        result = explain_lock_decision(
            **self._files(tmp_path),
            sick_history=SickHistory(),
            extended_early_bird=False,
            weekly_minimum_met=False,
            relaxed_day=False,
        )

        assert result.sources_degraded is False


class TestFirebaseDegradationIsVisible:
    """Losing the primary backend must leave a trace the caller can act on."""

    def test_degradation_is_recorded_not_just_logged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dead Firebase must be queryable, not only a log line.

        The 2026-08-24 run *did* warn. Nothing read the warning, so the lock
        decision was made as if the source were healthy. Recording the failure
        in state is what lets the decision layer tell the two cases apart.
        """
        _firebase_config(_sync_client, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            message = "failed to sign in: HTTP 400 (INVALID_LOGIN_CREDENTIALS)"
            raise FirebaseAuthError(message)

        monkeypatch.setattr(_sync_client, "mirror_client_for", _boom)
        _sync_client.clear_degraded_sources()
        github = object()

        assert _workout_sync.remote_client(github) is github
        degraded = _sync_client.degraded_sources()
        assert degraded, "a failed Firebase sign-in must be recorded"
        assert "INVALID_LOGIN_CREDENTIALS" in degraded[0].reason

    def test_healthy_firebase_records_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The happy path must stay silent, or the signal means nothing."""
        _firebase_config(_sync_client, tmp_path, monkeypatch)
        monkeypatch.setattr(
            _sync_client,
            "mirror_client_for",
            lambda _app, client: ("mirror", client),
        )
        _sync_client.clear_degraded_sources()

        _workout_sync.remote_client(object())

        assert _sync_client.degraded_sources() == []

    def test_unconfigured_machine_is_not_degraded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No Firebase config is a choice, not a failure -- do not cry wolf."""
        monkeypatch.setattr(
            _workout_sync, "CONFIG_FILE", Path("/nonexistent/firebase.json")
        )
        _sync_client.clear_degraded_sources()

        _workout_sync.remote_client(object())

        assert _sync_client.degraded_sources() == []
