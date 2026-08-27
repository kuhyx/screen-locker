"""Recovery keeps trying when a donor credential has gone stale.

Split from ``test_credential_recovery.py`` (250-line cap). Covers the two
behaviours added after 2026-08-27: falling through to the next sibling when
one refresh token is rejected, and the real token-exchange closure that
rewrites this machine's cached session.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from screen_locker._credential_recovery import recover_session
from screen_locker.tests._credential_fixtures import write_cache as _write_cache

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestDonorFallback:
    """One stale sibling must not defeat a recovery the others could finish."""

    def test_tries_the_next_sibling_when_the_first_is_rejected(
        self, tmp_path: Path
    ) -> None:
        """A dead donor is skipped, not treated as the final answer.

        The caches on a real machine are of mixed vintages, so the
        alphabetically-first one is not necessarily live. Stopping at it is
        the same "one dead source blocks the healthy ones" bug this module
        exists to fix.
        """
        _write_cache(
            tmp_path / "aaa_stale" / "firebase_auth.json",
            "refresh-stale",
            expires_at="2026-08-24T12:00:00+00:00",
        )
        _write_cache(
            tmp_path / "zzz_live" / "firebase_auth.json",
            "refresh-live",
            expires_at="2026-08-24T12:00:00+00:00",
        )

        def _mint(refresh_token: str) -> None:
            if refresh_token.endswith("-stale"):
                message = "TOKEN_EXPIRED"
                raise RuntimeError(message)

        result = recover_session(
            config_root=tmp_path, app_name="screen_locker", mint=_mint
        )

        assert result.recovered is True
        assert result.donor == "zzz_live"

    def test_reports_every_rejection_when_all_donors_are_dead(
        self, tmp_path: Path
    ) -> None:
        """Exhausting the donors must name them, not just say "failed"."""
        for app in ("aaa_stale", "zzz_stale"):
            _write_cache(
                tmp_path / app / "firebase_auth.json",
                f"refresh-{app}",
                expires_at="2026-08-24T12:00:00+00:00",
            )

        def _mint(_refresh_token: str) -> None:
            message = "TOKEN_EXPIRED"
            raise RuntimeError(message)

        result = recover_session(
            config_root=tmp_path, app_name="screen_locker", mint=_mint
        )

        assert result.recovered is False
        assert "aaa_stale" in result.reason
        assert "zzz_stale" in result.reason


class TestTryRecoverFirebaseSession:
    """The one impure step: exchanging a borrowed token for our own session."""

    def test_mints_and_caches_a_session_from_a_sibling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A successful exchange must persist the session under OUR app name.

        Exercised end to end (minus the HTTP call) because this closure is
        what actually rewrites ``~/.config/screen_locker/firebase_auth.json``.
        The autouse HOME redirect is what keeps that write inside tmp_path
        instead of clobbering the machine's live credential -- the exact
        accident this suite caused on 2026-08-27.
        """
        from screen_locker import _sync_client

        _write_cache(
            tmp_path / ".config" / "diet_guard" / "firebase_auth.json",
            "refresh-from-sibling",
            expires_at="2026-08-27T12:00:00+00:00",
        )
        posted: list[dict[str, str]] = []

        class _Response:
            def raise_for_status(self) -> None:
                """Report the exchange as successful."""

            def json(self) -> dict[str, str]:
                """Return a freshly minted session."""
                minted = "minted"
                return {
                    "id_token": f"{minted}-id-token",
                    "refresh_token": f"{minted}-refresh-token",
                    "expires_in": "3600",
                }

        def _post(
            _url: str, *, data: dict[str, str], timeout: float = 0.0
        ) -> _Response:
            del timeout
            posted.append(dict(data))
            return _Response()

        monkeypatch.setattr(_sync_client.requests, "post", _post)
        monkeypatch.setattr(
            _sync_client.FirebaseConfig,
            "load",
            classmethod(lambda _cls: SimpleNamespace(api_key="test-api-key")),
        )

        result = _sync_client.try_recover_firebase_session()

        assert result.recovered is True
        assert result.donor == "diet_guard"
        assert posted[0].get("grant_type") == "refresh_token"
        assert "refresh-from-sibling" in posted[0].values()
        written = tmp_path / ".config" / "screen_locker" / "firebase_auth.json"
        assert "minted-refresh-token" in written.read_text()
