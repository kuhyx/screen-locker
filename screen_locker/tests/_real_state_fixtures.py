"""Autouse fixtures whose one job is keeping tests off real user state.

Split out of ``conftest.py`` for the 250-line cap, and grouped because they
answer the same question in two different ways: what stops this suite from
reading or overwriting the developer's own files? Loaded through
``pytest_plugins`` in ``conftest.py``, so both stay autouse for every test.

The two seams are genuinely different, which is why neither subsumes the
other. ``_isolate_home`` covers paths resolved at *call* time from
``Path.home()``; ``_no_free_days_by_default`` covers paths bound into module
constants at *import* time, which redirecting home afterwards cannot reach.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _no_free_days_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let the lock chain read the developer's real free-day pool.

    ``_isolate_home`` cannot cover this one. freedays binds its paths from
    ``Path.home()`` at *import* time into module constants, so redirecting
    home afterwards leaves them pointing at the real
    ``~/.local/share/freedays``. Every writer resolves through
    ``resolve_paths``, so that is the seam.

    Without it, a real free day on this machine would short-circuit the lock
    chain in every test here -- it is the very first check in the chain --
    and the failures would name early-bird and sick-day logic instead.
    """
    import freedays._api

    monkeypatch.setattr(
        freedays._api,
        "resolve_paths",
        lambda paths: paths or freedays.Paths.under(tmp_path / "freedays"),
    )


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point ``$HOME`` and ``Path.home()`` at tmp_path for every test.

    ``ISOLATED_STATE`` cannot cover this. Everything under ``~/.config`` is
    resolved at *call* time by ``crdt_sync.credential_store_for``
    (``Path.home() / ".config" / app / "firebase_auth.json"``), not bound to a
    module-level constant, so there is no attribute to patch -- the only seam
    is home itself.

    What this protects is a live credential, not a scratch file. A test that
    reaches ``credential_store_for("screen_locker")`` and saves would overwrite
    the machine's real Firebase session with fixture values, and the damage is
    invisible until the next sync fails with HTTP 401. The same redirect also
    covers the sync PAT and the shared ``~/.config/crdt-sync/`` password and
    OAuth secret, which are read the same way.

    ``Path.home()`` is patched as well as ``$HOME``: it consults ``os.environ``
    on POSIX, but only via ``expanduser``, and a test that patches the
    environment differently must not silently regain access to the real one.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch.object(Path, "home", lambda: tmp_path):
        yield
