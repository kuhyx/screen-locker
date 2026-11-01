"""Poke HTTP routing and framing: paths, methods, Content-Length and body limits."""

from __future__ import annotations

from http.client import HTTPConnection
import json
from typing import TYPE_CHECKING

import pytest

from screen_locker import _poke_server
from screen_locker._poke_server import MAX_BODY_BYTES, POKE_PATH
from screen_locker.tests.test_poke_server import (
    _body,
    _post,
    _raw,
    _sign,
    credit_fixture,
    port_fixture,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

__all__ = ["credit_fixture", "port_fixture"]


class TestRouting:
    """Path, method and Content-Length handling before any body is judged."""

    def test_unknown_path_is_404(self, port: int, credit: MagicMock) -> None:
        """A POST to an unknown path is a 404 naming the path."""
        body = _body()
        status, reply = _post(port, body, _sign(body), path="/v2/other")
        assert status == 404
        assert "unknown path" in reply["reason"]

    def test_get_is_405(self, port: int) -> None:
        """A GET is refused with 405 saying only POST is accepted."""
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", POKE_PATH)
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        assert resp.status == 405
        assert "only POST" in data["reason"]

    def test_missing_content_length_is_411(self, port: int) -> None:
        """A POST without Content-Length is a 411."""
        status, _ = _raw(port, ["Host: x"])
        assert status == 411

    @pytest.mark.parametrize("value", ["abc", "-5", ""])
    def test_malformed_content_length_is_400(self, port: int, value: str) -> None:
        """A non-numeric, negative or empty Content-Length is a 400."""
        status, reply = _raw(port, [f"Content-Length: {value}"])
        assert status == 400
        assert "bad Content-Length" in reply["reason"]

    def test_oversized_body_is_413_without_reading_it(self, port: int) -> None:
        """A declared body over the cap is refused with 413 before reading it."""
        status, reply = _raw(port, [f"Content-Length: {MAX_BODY_BYTES + 1}"])
        assert status == 413
        assert str(MAX_BODY_BYTES) in reply["reason"]

    def test_body_at_the_cap_is_read_and_judged_on_its_signature(
        self, port: int
    ) -> None:
        """A body exactly at the cap is read and then judged on content, not size."""
        body = b"x" * MAX_BODY_BYTES
        assert _post(port, body, _sign(body))[0] == 400

    def test_truncated_body_is_400(self, port: int) -> None:
        """A body shorter than its Content-Length is a 400 reporting the byte counts."""
        status, reply = _raw(port, ["Content-Length: 100"], send=b"0123456789")
        assert status == 400
        assert "10 of 100 bytes" in reply["reason"]


def test_reply_for_a_refusal_leaves_the_snapshot_null() -> None:
    """A refusal reply carries no shutdown or gaming-budget snapshot."""
    reply = _poke_server._refused("nope")
    assert reply["ok"] is False
    assert (reply["shutdown"], reply["gaming_budget_minutes"]) == (None, None)
    assert reply["reason"] == "nope"
