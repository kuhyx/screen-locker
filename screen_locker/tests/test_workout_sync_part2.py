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

from screen_locker import _workout_sync
from screen_locker.tests._workout_sync_fixtures import (
    _firebase_config,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestSyncClient:
    """Every configuration of (GitHub token, Firebase config), plus failure."""

    def test_returns_none_when_nothing_is_configured(self) -> None:
        """Returns none when nothing is configured."""
        assert _workout_sync.sync_client() is None

    def test_warns_when_nothing_is_configured(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warns when nothing is configured."""
        with caplog.at_level("WARNING"):
            _workout_sync.sync_client()
        assert "sync is OFF" in caplog.text

    def test_uses_github_alone_when_only_the_token_exists(self) -> None:
        """Uses github alone when only the token exists."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        github = MagicMock()
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=github):
            assert _workout_sync.sync_client() is github

    def test_mirrors_when_both_the_token_and_firebase_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mirrors when both the token and firebase exist."""
        _workout_sync.SYNC_TOKEN_FILE.write_text("tok")
        _firebase_config(_workout_sync, tmp_path, monkeypatch)
        github = MagicMock()
        monkeypatch.setattr(
            _workout_sync, "mirror_client_for", lambda _app, client: ("mirror", client)
        )
        with patch.object(_workout_sync, "GitHubSyncClient", return_value=github):
            assert _workout_sync.sync_client() == ("mirror", github)

    def test_uses_firebase_alone_when_only_the_config_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A Firebase-only machine must still sync -- no PAT required."""
        _firebase_config(_workout_sync, tmp_path, monkeypatch)
        firebase = MagicMock()
        monkeypatch.setattr(_workout_sync, "firebase_client_for", lambda _app: firebase)
        assert _workout_sync.sync_client() is firebase

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
        """No PAT to fall back to: report it loudly, do not raise."""
        _firebase_config(_workout_sync, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise error

        monkeypatch.setattr(_workout_sync, "firebase_client_for", _boom)
        assert _workout_sync.sync_client() is None

    def test_warns_when_firebase_only_is_unusable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Warns when firebase only is unusable."""
        _firebase_config(_workout_sync, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            message = "backend down"
            raise FirebaseSyncError(message)

        monkeypatch.setattr(_workout_sync, "firebase_client_for", _boom)
        with caplog.at_level("WARNING"):
            _workout_sync.sync_client()
        assert "backend down" in caplog.text
