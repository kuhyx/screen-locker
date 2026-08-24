"""A dead Firebase credential must heal itself, not wait for a human.

On 2026-08-24 the PC could not read Firebase because ``screen_locker`` had no
cached session and the shared password no longer authenticated. Every sibling
app on the same machine -- ``diet_guard``, ``wake_alarm``, ``todo`` -- held a
live refresh token for the *same* account and project the whole time. The
credential was on disk, three directories away, and nothing looked for it.

Recovery is therefore local and needs no human: borrow a sibling's refresh
token, mint a session, and cache it under our own app name.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from screen_locker._credential_recovery import (
    find_sibling_refresh_token,
    recover_session,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write_cache(path: Path, refresh_token: str, *, expires_at: str) -> None:
    """Write a credential cache shaped like ``FileCredentialStore``'s."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id_token": "stale-id-token",
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "local_id": "uid-1",
            }
        )
    )


class TestFindSiblingRefreshToken:
    """Locating a live credential already present on this machine."""

    def test_finds_a_sibling_apps_token(self, tmp_path: Path) -> None:
        """Any sibling app's cache is a valid source -- one account, one project."""
        _write_cache(
            tmp_path / "diet_guard" / "firebase_auth.json",
            "refresh-abc",
            expires_at="2026-08-24T12:00:00+00:00",
        )

        found = find_sibling_refresh_token(tmp_path, skip="screen_locker")

        assert found == ("diet_guard", "refresh-abc")

    def test_ignores_our_own_stale_cache(self, tmp_path: Path) -> None:
        """Our own dead cache is the thing being replaced, never the source."""
        _write_cache(
            tmp_path / "screen_locker" / "firebase_auth.json",
            "refresh-ours",
            expires_at="2026-08-24T12:00:00+00:00",
        )

        assert find_sibling_refresh_token(tmp_path, skip="screen_locker") is None

    def test_skips_unreadable_and_malformed_caches(self, tmp_path: Path) -> None:
        """A corrupt sibling must not abort the search over the healthy ones."""
        bad = tmp_path / "broken_app" / "firebase_auth.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{not json")
        _write_cache(
            tmp_path / "wake_alarm" / "firebase_auth.json",
            "refresh-xyz",
            expires_at="2026-08-24T12:00:00+00:00",
        )

        found = find_sibling_refresh_token(tmp_path, skip="screen_locker")

        assert found == ("wake_alarm", "refresh-xyz")

    def test_reports_nothing_when_no_sibling_has_one(self, tmp_path: Path) -> None:
        """No source is a real outcome; the caller must hear it, not guess."""
        assert find_sibling_refresh_token(tmp_path, skip="screen_locker") is None


class TestRecoverSession:
    """Turning a borrowed refresh token into our own cached session."""

    def test_recovers_and_reports_the_donor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A successful recovery must say where the credential came from."""
        _write_cache(
            tmp_path / "diet_guard" / "firebase_auth.json",
            "refresh-abc",
            expires_at="2026-08-24T12:00:00+00:00",
        )
        minted: list[str] = []

        def _mint(refresh_token: str) -> None:
            minted.append(refresh_token)

        result = recover_session(
            config_root=tmp_path, app_name="screen_locker", mint=_mint
        )

        assert result.recovered is True
        assert result.donor == "diet_guard"
        assert minted == ["refresh-abc"]

    def test_failure_explains_itself(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed recovery must carry a reason a human can act on."""

        def _mint(_refresh_token: str) -> None:
            message = "TOKEN_EXPIRED"
            raise RuntimeError(message)

        _write_cache(
            tmp_path / "diet_guard" / "firebase_auth.json",
            "refresh-abc",
            expires_at="2026-08-24T12:00:00+00:00",
        )

        result = recover_session(
            config_root=tmp_path, app_name="screen_locker", mint=_mint
        )

        assert result.recovered is False
        assert "TOKEN_EXPIRED" in result.reason

    def test_no_donor_is_reported_not_swallowed(self, tmp_path: Path) -> None:
        """ "Nothing to borrow" must be a stated reason, never a silent False."""
        result = recover_session(
            config_root=tmp_path, app_name="screen_locker", mint=lambda _t: None
        )

        assert result.recovered is False
        assert "no sibling" in result.reason.lower()
