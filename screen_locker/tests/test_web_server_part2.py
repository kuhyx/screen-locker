"""Tests for _web_server static serving: SPA fallback and traversal guard.

Split out of test_web_server.py for the 250-line cap; the server harness and
the real_loopback fixture stay in that module and are imported here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from screen_locker.tests.test_web_server import (
    _PKG,
    _get,
    _make_dist,
    _running,
    real_loopback,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["real_loopback"]


class TestStaticServing:
    """The built bundle is served with an SPA fallback and a traversal guard."""

    @pytest.fixture(autouse=True)
    def _network(self, real_loopback: None) -> None:
        """Every test in this class talks to the server over real HTTP."""

    def test_index_is_served_at_the_root(self, tmp_path: Path) -> None:
        """/ serves index.html."""
        with patch(f"{_PKG}.WEB_DIST", _make_dist(tmp_path)), _running() as port:
            status, body, ctype = _get(port, "/")
        assert status == 200
        assert b"INDEX" in body
        assert ctype.startswith("text/html")

    def test_an_asset_is_served_with_its_own_type(self, tmp_path: Path) -> None:
        """A real file is served rather than the SPA fallback."""
        with patch(f"{_PKG}.WEB_DIST", _make_dist(tmp_path)), _running() as port:
            status, body, ctype = _get(port, "/app.css")
        assert status == 200
        assert body == b"body{}"
        assert ctype.startswith("text/css")

    def test_a_binary_asset_gets_no_charset(self, tmp_path: Path) -> None:
        """A charset on image/png would be wrong; only text types get one."""
        with patch(f"{_PKG}.WEB_DIST", _make_dist(tmp_path)), _running() as port:
            status, body, ctype = _get(port, "/icon.png")
        assert status == 200
        assert body.startswith(b"\x89PNG")
        assert ctype == "image/png"

    def test_an_unknown_route_falls_back_to_index(self, tmp_path: Path) -> None:
        """SPA routes are handled by the bundle, not by the server."""
        with patch(f"{_PKG}.WEB_DIST", _make_dist(tmp_path)), _running() as port:
            status, body, _ = _get(port, "/why/2026-08-29")
        assert status == 200
        assert b"INDEX" in body

    def test_traversal_never_escapes_the_bundle(self, tmp_path: Path) -> None:
        """A ../ path is refused, not resolved against the filesystem."""
        secret = tmp_path / "secret.txt"
        secret.write_text("do not serve me", encoding="utf-8")
        with patch(f"{_PKG}.WEB_DIST", _make_dist(tmp_path)), _running() as port:
            status, body, _ = _get(port, "/../secret.txt")
        assert status == 200
        assert b"do not serve me" not in body

    def test_missing_bundle_says_how_to_build_it(self, tmp_path: Path) -> None:
        """404 carries the build command instead of an empty page."""
        dist = _make_dist(tmp_path, with_index=False)
        with patch(f"{_PKG}.WEB_DIST", dist), _running() as port:
            status, body, _ = _get(port, "/")
        assert status == 404
        assert b"npm --prefix web run build" in body
