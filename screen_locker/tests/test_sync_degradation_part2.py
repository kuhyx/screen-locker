"""A Firebase credential that BUILDS but is refused must still self-heal.

Split from ``test_sync_degradation.py`` (250-line cap).

``mirror_client_for`` only checks ``has_session()``, which reads the cached
JSON off disk and never reaches the network. So on 2026-08-27 a credential the
server had stopped accepting constructed perfectly, the recovery -- wired only
to construction failures -- never ran, and every read and write was refused
with HTTP 401 for weeks behind a warning nobody read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from screen_locker import _startup_checks, _sync_client, _workout_sync
from screen_locker._credential_recovery import RecoveryResult
from screen_locker._degraded_sources import _record_degraded
from screen_locker.tests._workout_sync_fixtures import (
    ReachableClient,
    RejectedClient,
    _firebase_config,
)
from screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestRejectedCredentialTriggersRecovery:
    """A credential that builds but is refused must heal, not 401 forever."""

    def test_a_rejected_credential_is_recovered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This is 2026-08-27: present on disk, rejected by the server.

        ``mirror_client_for`` only checks ``has_session()``, which reads the
        cached JSON and never reaches the network, so construction SUCCEEDED
        and the recovery -- wired only to construction failures -- never ran
        while every read and write was being refused with HTTP 401.
        """
        _firebase_config(_sync_client, tmp_path, monkeypatch)
        built: list[int] = []

        def _rejected_then_live(_app: object, _client: object) -> object:
            built.append(1)
            return RejectedClient() if len(built) == 1 else ReachableClient()

        monkeypatch.setattr(_sync_client, "mirror_client_for", _rejected_then_live)
        monkeypatch.setattr(
            _sync_client,
            "try_recover_firebase_session",
            lambda: RecoveryResult(recovered=True, reason="rebuilt from a sibling"),
        )
        _sync_client.clear_degraded_sources()

        client = _workout_sync.remote_client(object())

        assert isinstance(client, ReachableClient), (
            "a rejected credential must trigger the same self-heal as a "
            "failed construction"
        )
        assert _sync_client.degraded_sources() == []

    def test_a_still_rejected_credential_is_degraded_loudly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If it is still refused after healing, say so on the lock screen.

        Falling back to GitHub silently is what let weeks of 401s scroll past
        in a journal nobody reads.
        """
        _firebase_config(_sync_client, tmp_path, monkeypatch)
        monkeypatch.setattr(
            _sync_client,
            "mirror_client_for",
            lambda _app, _client: RejectedClient(),
        )
        monkeypatch.setattr(
            _sync_client,
            "try_recover_firebase_session",
            lambda: RecoveryResult(recovered=True, reason="rebuilt from a sibling"),
        )
        _sync_client.clear_degraded_sources()
        github = object()

        assert _workout_sync.remote_client(github) is github
        degraded = _sync_client.degraded_sources()
        assert degraded, "a credential the server refuses must be recorded"
        assert "rejected" in degraded[0].reason


class TestDecisionNamesUnreadableSources:
    """A weekly count taken over a dead backend is a floor, not a count.

    On 2026-08-24 the only trace of a dead Firebase was a warning 90 seconds
    earlier, and the DECISION line read ``weekly=0/5`` as though that zero
    were a measurement. The decision itself has to say which source it could
    not read.
    """

    def test_a_degraded_source_is_named_on_the_decision(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """The annotation exists precisely so the zero cannot mislead."""
        locker = create_locker(mock_tk, tmp_path, has_logged=True)
        _record_degraded("firebase", "credential refused")
        with patch.object(_startup_checks, "record_decision") as recorded:
            locker._record_decision(
                locked=True, reason="enforced", detail="No exemption applied."
            )
        assert recorded.call_args.args[0].extra["unreadable_sources"] == "firebase"

    def test_a_healthy_run_adds_no_such_note(
        self, mock_tk: MagicMock, mock_sys_exit: MagicMock, tmp_path: Path
    ) -> None:
        """Every decision must not carry an empty caveat."""
        locker = create_locker(mock_tk, tmp_path, has_logged=True)
        with patch.object(_startup_checks, "record_decision") as recorded:
            locker._record_decision(
                locked=True, reason="enforced", detail="No exemption applied."
            )
        assert "unreadable_sources" not in recorded.call_args.args[0].extra
