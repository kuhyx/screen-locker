"""``remote_client`` mirror selection, split from ``test_workout_sync_part2``.

Kept separate from the pulls so no workout-sync test file exceeds the repo's
400-line limit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from crdt_sync import ConfigError

from screen_locker import _workout_sync
from screen_locker.tests._workout_sync_fixtures import _firebase_config

if TYPE_CHECKING:
    import pytest


class TestRemoteClient:
    """Which backend the workout pull reads from during the cutover."""

    def test_stays_on_github_without_firebase_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unconfigured machine must not reach the network at all."""
        monkeypatch.setattr(
            _workout_sync, "CONFIG_FILE", Path("/nonexistent/firebase.json")
        )
        github = object()

        assert _workout_sync.remote_client(github) is github

    def test_mirrors_to_github_when_configured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Configured: reads union both, so either backend's workout counts."""
        _firebase_config(_workout_sync, tmp_path, monkeypatch)
        monkeypatch.setattr(
            _workout_sync,
            "mirror_client_for",
            lambda _app, client: ("mirror", client),
        )
        github = object()

        assert _workout_sync.remote_client(github) == ("mirror", github)

    def test_falls_back_when_firebase_is_unusable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken Firebase must degrade to GitHub, never fail the pull."""
        _firebase_config(_workout_sync, tmp_path, monkeypatch)

        def _boom(*_args: object, **_kwargs: object) -> None:
            message = "no password"
            raise ConfigError(message)

        monkeypatch.setattr(_workout_sync, "mirror_client_for", _boom)
        github = object()

        assert _workout_sync.remote_client(github) is github
