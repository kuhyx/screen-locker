"""Tests for _stream_auth: token, URL and renew deadline for the stream."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from crdt_sync import (
    ConfigError,
    FirebaseAuthError,
    FirebaseConfig,
    FirebaseCredentials,
)
import pytest

from screen_locker import _stream_auth
from screen_locker._credential_recovery import RecoveryResult
from screen_locker._stream_auth import StreamAuth, StreamError, stream_auth

_CONFIG = FirebaseConfig(
    api_key="key",
    database_url="https://db.example/",
    project_id="proj",
    uid="uid",
    email="me@example.com",
)
_EXPIRY = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def _provider(*, has_session: bool = True, minted: str = "TOKEN") -> MagicMock:
    """A token provider fake with a cached (or missing) session."""
    provider = MagicMock()
    provider.has_session.return_value = has_session
    provider.id_token.return_value = minted
    return provider


class _Fakes:
    """The patched collaborators of ``stream_auth``."""

    def __init__(self) -> None:
        self.store = MagicMock()
        self.store.load.return_value = FirebaseCredentials("id", "refresh", _EXPIRY)
        self.providers: list[MagicMock] = [_provider()]
        self.recovery = RecoveryResult(recovered=True, reason="ok", donor="todo")
        self.recover = MagicMock(side_effect=lambda: self.recovery)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> _Fakes:
    """Patch config loading, the credential store, providers and recovery."""
    fake = _Fakes()
    monkeypatch.setattr(
        _stream_auth.FirebaseConfig, "load", classmethod(lambda _cls: _CONFIG)
    )
    monkeypatch.setattr(_stream_auth, "credential_store_for", lambda _app: fake.store)
    monkeypatch.setattr(
        _stream_auth,
        "FirebaseTokenProvider",
        MagicMock(side_effect=lambda *_a, **_k: fake.providers.pop(0)),
    )
    monkeypatch.setattr(_stream_auth, "try_recover_firebase_session", fake.recover)
    return fake


class TestCachedSession:
    """The common path: the cache already holds a session."""

    def test_url_token_and_renew_at_from_saved_expiry(self, fakes: _Fakes) -> None:
        """The URL is the encoded path on the DB host; renew 4 min before expiry."""
        auth = stream_auth("screen-locker-sync/devices")
        assert auth == StreamAuth(
            "https://db.example/screen-locker-sync/devices.json",
            "TOKEN",
            _EXPIRY - timedelta(minutes=4),
        )
        fakes.recover.assert_not_called()

    def test_assumed_lifetime_when_nothing_is_saved(self, fakes: _Fakes) -> None:
        """No stored expiry: assume an hour, still renewing 4 minutes early."""
        fakes.store.load.return_value = None
        before = datetime.now(UTC)
        auth = stream_auth("a/b")
        after = datetime.now(UTC)
        lifetime = timedelta(hours=1) - timedelta(minutes=4)
        assert before + lifetime <= auth.renew_at <= after + lifetime


class TestRecovery:
    """A missing session is healed the way the sync heals it."""

    def test_recovered_session_is_used(self, fakes: _Fakes) -> None:
        """After recovery a fresh provider over the same store mints the token."""
        fakes.providers = [
            _provider(has_session=False),
            _provider(minted="RECOVERED"),
        ]
        auth = stream_auth("a/b")
        assert auth.url.endswith("/a/b.json")
        assert auth == StreamAuth(auth.url, "RECOVERED", auth.renew_at)
        fakes.recover.assert_called_once_with()

    def test_failed_recovery_is_a_stream_error_with_the_reason(
        self, fakes: _Fakes
    ) -> None:
        """No donor session: back off, and say why."""
        fakes.providers = [_provider(has_session=False)]
        fakes.recovery = RecoveryResult(recovered=False, reason="no donor found")
        with pytest.raises(StreamError, match="recovery failed: no donor found"):
            stream_auth("a/b")


class TestUnusableAuth:
    """Library errors become StreamError, keeping the cause."""

    def test_config_error(self, fakes: _Fakes, monkeypatch: pytest.MonkeyPatch) -> None:
        """A broken Firebase config file is a StreamError."""

        def boom(_cls: type[FirebaseConfig]) -> FirebaseConfig:
            msg = "placeholder key"
            raise ConfigError(msg)

        monkeypatch.setattr(_stream_auth.FirebaseConfig, "load", classmethod(boom))
        with pytest.raises(StreamError, match="config unusable: placeholder key") as ei:
            stream_auth("a/b")
        assert isinstance(ei.value.__cause__, ConfigError)

    def test_firebase_auth_error(self, fakes: _Fakes) -> None:
        """A refresh the server rejects is a StreamError."""
        fakes.providers[0].id_token.side_effect = FirebaseAuthError("revoked")
        with pytest.raises(StreamError, match="ID token: revoked") as ei:
            stream_auth("a/b")
        assert isinstance(ei.value.__cause__, FirebaseAuthError)
