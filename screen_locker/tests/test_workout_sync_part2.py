"""Backend selection and the two public pulls, split from ``test_workout_sync``.

``sync_client`` decides WHICH backend is read; ``pull_synced_workout`` and
``pull_all_manual_records`` are what the locker actually calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from crdt_sync import (
    ConfigError,
    FirebaseAuthError,
    FirebaseSyncError,
)
import pytest

from screen_locker import _sync_client, _workout_sync
from screen_locker.tests._workout_sync_fixtures import (
    _firebase_config,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestSyncClient:
    """Firebase is the only backend: configured, missing, or unusable."""

    def test_returns_none_when_nothing_is_configured(self) -> None:
        """Returns none when nothing is configured."""
        assert _workout_sync.sync_client() is None

    def test_warns_when_nothing_is_configured(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The warning names BOTH directions that stop syncing."""
        with caplog.at_level("WARNING"):
            _workout_sync.sync_client()
        assert "Sync is OFF" in caplog.text
        assert "will NOT be pushed" in caplog.text
        assert "NOT be pulled" in caplog.text

    def test_reason_names_the_missing_config(self) -> None:
        """The reason is a sentence a caller can put into its own result."""
        client, reason = _workout_sync.sync_client_or_reason()
        assert client is None
        assert reason.startswith("no Firebase config at ")

    def test_never_builds_a_client_without_config(self) -> None:
        """An unconfigured machine must not reach the network at all."""
        with patch.object(_sync_client, "firebase_client_for") as build:
            _workout_sync.sync_client()
        build.assert_not_called()

    def test_uses_firebase_when_the_config_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A configured machine syncs over Firebase -- no PAT anywhere."""
        _firebase_config(_sync_client, tmp_path, monkeypatch)
        firebase = MagicMock()
        monkeypatch.setattr(
            _sync_client, "firebase_client_for", lambda *_a, **_k: firebase
        )
        assert _workout_sync.sync_client() is firebase
        assert _workout_sync.sync_client_or_reason() == (firebase, "")

    @pytest.mark.parametrize(
        "error",
        [
            ConfigError("no password"),
            FirebaseAuthError("bad credentials"),
            FirebaseSyncError("backend down"),
        ],
    )
    def test_returns_none_when_firebase_only_is_unusable(
        self, error: Exception, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No fallback exists: report it loudly, do not raise."""
        _firebase_config(_sync_client, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise error

        monkeypatch.setattr(_sync_client, "firebase_client_for", _boom)
        client, reason = _workout_sync.sync_client_or_reason()
        assert client is None
        assert reason.startswith("Firebase unusable: ")

    def test_warns_when_firebase_only_is_unusable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Warns when firebase only is unusable."""
        _firebase_config(_sync_client, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            message = "backend down"
            raise FirebaseSyncError(message)

        monkeypatch.setattr(_sync_client, "firebase_client_for", _boom)
        with caplog.at_level("WARNING"):
            _workout_sync.sync_client()
        assert "backend down" in caplog.text
