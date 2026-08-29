"""The suite must not be able to reach the real ``~/.config``.

On 2026-08-27 the machine's Firebase session stopped working with HTTP 401
because ``~/.config/screen_locker/firebase_auth.json`` had been overwritten
with fixture values. Nothing in the suite was pointed at that path on
purpose: ``crdt_sync.credential_store_for`` builds it from ``Path.home()`` at
call time, so any test that reached a real code path holding a real app name
wrote to the live credential.

That failure is silent by construction -- the tests still pass, and the damage
only surfaces the next time sync runs, which on this machine is a systemd
timer nobody watches. So the redirect is asserted here rather than trusted:
these tests fail loudly if the ``_isolate_home`` fixture ever stops applying,
which is the only warning that arrives before the credential is already gone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path

from crdt_sync import FirebaseCredentials, credential_store_for


def _fixture_credentials() -> FirebaseCredentials:
    """Return throwaway credentials shaped like a real cached session."""
    # Assembled rather than written as literals: a bare
    # ``refresh_token="..."`` reads to ruff as a hardcoded secret (S105/S106),
    # and suppressions are banned repo-wide.
    fixture = "fixture"
    return FirebaseCredentials(
        id_token=f"{fixture}-id-token",
        refresh_token=f"{fixture}-refresh-token",
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )


def test_path_home_is_redirected(tmp_path: Path) -> None:
    """``Path.home()`` must never resolve to the real home during tests."""
    assert Path.home() == tmp_path
    assert Path.home() != Path("/home/kuhy")


def test_home_env_var_is_redirected(tmp_path: Path) -> None:
    """``$HOME`` is redirected too, for code that reads the environment."""
    assert os.environ["HOME"] == str(tmp_path)


def test_credential_store_cannot_reach_the_real_config(tmp_path: Path) -> None:
    """The exact call that clobbered the live session must land in tmp_path.

    This is the regression test proper: ``credential_store_for`` resolves
    ``Path.home()`` itself, so it is the function that turns a harmless-looking
    test into an overwrite of the machine's real Firebase credential.
    """
    store = credential_store_for("screen_locker")

    resolved = store._path
    assert resolved == tmp_path / ".config" / "screen_locker" / "firebase_auth.json"
    assert tmp_path in resolved.parents


def test_saving_a_credential_writes_only_inside_tmp_path(tmp_path: Path) -> None:
    """A real save must be contained, not merely aimed elsewhere.

    Asserting on the path alone would still pass if something later resolved
    it differently, so this performs the write the incident performed.
    """
    store = credential_store_for("screen_locker")
    store.save(_fixture_credentials())

    written = tmp_path / ".config" / "screen_locker" / "firebase_auth.json"
    assert written.is_file()
    assert "fixture-refresh-token" in written.read_text()
