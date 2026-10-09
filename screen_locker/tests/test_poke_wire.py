"""The poke wire checks: signature, freshness, replay and schema, in order."""

from __future__ import annotations

import hashlib
import hmac
from http import HTTPStatus
import json
from typing import Any

import pytest

from screen_locker._poke_wire import (
    REPLAY_WINDOW_MS,
    NonceCache,
    PokeRequest,
    Rejection,
    check_request,
    parse_key,
    verify_signature,
)

_KEY = bytes(range(32))
_NOW = 1_800_000_000_000


def _doc(**overrides: object) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "v": 1,
        "sent_at_ms": _NOW,
        "nonce": "n-1",
        "sandbox": False,
        "record_id": "rec-1",
        "payload": {"date": "2026-10-09"},
    }
    doc.update(overrides)
    return doc


def _sign(body: bytes, key: bytes = _KEY) -> str:
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def _check(
    doc: dict[str, Any] | bytes,
    *,
    nonces: NonceCache | None = None,
    now_ms: int = _NOW,
) -> PokeRequest | Rejection:
    body = doc if isinstance(doc, bytes) else json.dumps(doc).encode("utf-8")
    return check_request(
        _KEY, body, _sign(body), NonceCache() if nonces is None else nonces, now_ms
    )


def _rejected(result: PokeRequest | Rejection, status: HTTPStatus) -> Rejection:
    assert isinstance(result, Rejection)
    assert result.status is status
    return result


class TestParseKey:
    def test_decodes_64_hex_chars_with_surrounding_whitespace(self) -> None:
        assert parse_key(f"  {_KEY.hex()}\n") == _KEY

    def test_wrong_length_says_how_long_it_was(self) -> None:
        with pytest.raises(ValueError, match="got 4"):
            parse_key("abcd")

    def test_non_hex_of_the_right_length_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not valid hex"):
            parse_key("zz" * 32)


class TestVerifySignature:
    def test_matching_mac_verifies(self) -> None:
        assert verify_signature(_KEY, b"body", _sign(b"body"))

    def test_uppercase_and_padded_header_is_accepted(self) -> None:
        assert verify_signature(_KEY, b"body", f" {_sign(b'body').upper()} ")

    @pytest.mark.parametrize("header", [None, ""])
    def test_missing_header_is_false(self, header: str | None) -> None:
        assert not verify_signature(_KEY, b"body", header)

    def test_wrong_key_is_false(self) -> None:
        assert not verify_signature(_KEY, b"body", _sign(b"body", b"k" * 32))

    def test_non_ascii_header_is_false_not_an_exception(self) -> None:
        assert not verify_signature(_KEY, b"body", "é" * 64)
        assert not verify_signature(_KEY, b"body", "☃" * 64)


class TestNonceCache:
    def test_second_use_inside_window_is_refused(self) -> None:
        cache = NonceCache()
        assert cache.check_and_add("a", _NOW, _NOW)
        assert not cache.check_and_add("a", _NOW, _NOW + 1)
        assert len(cache) == 1

    def test_pruned_by_sent_at_after_the_window(self) -> None:
        cache = NonceCache()
        cache.check_and_add("a", _NOW, _NOW)
        assert cache.check_and_add("b", _NOW, _NOW + REPLAY_WINDOW_MS)
        assert len(cache) == 2
        assert cache.check_and_add("a", _NOW, _NOW + REPLAY_WINDOW_MS + 1)
        assert len(cache) == 1  # both old entries pruned, only the new "a" stays

    def test_future_stamped_nonce_is_remembered_until_sent_at_plus_window(
        self,
    ) -> None:
        cache = NonceCache()
        future = _NOW + 100_000
        cache.check_and_add("a", future, _NOW)
        assert not cache.check_and_add("a", future, _NOW + 150_000)


class TestCheckRequest:
    def test_valid_request_is_parsed(self) -> None:
        result = _check(_doc(sandbox=True))
        assert isinstance(result, PokeRequest)
        assert (result.nonce, result.record_id) == ("n-1", "rec-1")
        assert result.sandbox is True
        assert result.payload == {"date": "2026-10-09"}

    def test_bad_signature_is_401_and_parses_nothing(self) -> None:
        body = b"not json at all"
        result = check_request(_KEY, body, "00" * 32, NonceCache(), _NOW)
        assert "signature" in _rejected(result, HTTPStatus.UNAUTHORIZED).reason

    def test_bad_signature_beats_every_later_check(self) -> None:
        body = json.dumps(_doc(sent_at_ms=0)).encode()
        result = check_request(_KEY, body, None, NonceCache(), _NOW)
        assert "signature" in _rejected(result, HTTPStatus.UNAUTHORIZED).reason

    def test_signed_non_utf8_is_400(self) -> None:
        reason = _rejected(_check(b"\xff\xfe"), HTTPStatus.BAD_REQUEST).reason
        assert "UTF-8 JSON" in reason

    def test_signed_invalid_json_is_400(self) -> None:
        _rejected(_check(b"{nope"), HTTPStatus.BAD_REQUEST)

    def test_signed_json_array_is_400(self) -> None:
        reason = _rejected(_check(b"[1]"), HTTPStatus.BAD_REQUEST).reason
        assert "not a JSON object" in reason

    @pytest.mark.parametrize("value", [None, "1", True, 1.5])
    def test_sent_at_must_be_a_real_int(self, value: object) -> None:
        reason = _rejected(
            _check(_doc(sent_at_ms=value)), HTTPStatus.BAD_REQUEST
        ).reason
        assert "sent_at_ms" in reason

    @pytest.mark.parametrize("skew", [REPLAY_WINDOW_MS + 1, -REPLAY_WINDOW_MS - 1])
    def test_stale_or_future_stamp_is_401_naming_the_clock(self, skew: int) -> None:
        result = _check(_doc(sent_at_ms=_NOW - skew))
        assert "stale" in _rejected(result, HTTPStatus.UNAUTHORIZED).reason

    @pytest.mark.parametrize("skew", [REPLAY_WINDOW_MS, -REPLAY_WINDOW_MS])
    def test_exactly_the_window_edge_is_still_fresh(self, skew: int) -> None:
        assert isinstance(_check(_doc(sent_at_ms=_NOW - skew)), PokeRequest)

    @pytest.mark.parametrize("nonce", [None, "", 7])
    def test_nonce_must_be_a_non_empty_string(self, nonce: object) -> None:
        _rejected(_check(_doc(nonce=nonce)), HTTPStatus.BAD_REQUEST)

    def test_replayed_nonce_is_409(self) -> None:
        nonces = NonceCache()
        assert isinstance(_check(_doc(), nonces=nonces), PokeRequest)
        result = _check(_doc(), nonces=nonces)
        assert "already used" in _rejected(result, HTTPStatus.CONFLICT).reason

    def test_staleness_is_checked_before_replay(self) -> None:
        nonces = NonceCache()
        _check(_doc(), nonces=nonces)
        stale = _doc(sent_at_ms=_NOW - REPLAY_WINDOW_MS - 1)
        _rejected(_check(stale, nonces=nonces), HTTPStatus.UNAUTHORIZED)

    @pytest.mark.parametrize("version", [None, 2, "1", True])
    def test_unsupported_version_is_400(self, version: object) -> None:
        reason = _rejected(_check(_doc(v=version)), HTTPStatus.BAD_REQUEST).reason
        assert "protocol version" in reason

    @pytest.mark.parametrize("sandbox", [None, "false", 0])
    def test_sandbox_must_be_a_bool(self, sandbox: object) -> None:
        reason = _rejected(_check(_doc(sandbox=sandbox)), HTTPStatus.BAD_REQUEST).reason
        assert "'sandbox'" in reason

    @pytest.mark.parametrize("record_id", [None, "", 5])
    def test_record_id_must_be_a_non_empty_string(self, record_id: object) -> None:
        reason = _rejected(
            _check(_doc(record_id=record_id)), HTTPStatus.BAD_REQUEST
        ).reason
        assert "'record_id'" in reason

    @pytest.mark.parametrize("payload", [None, [], "x"])
    def test_payload_must_be_an_object(self, payload: object) -> None:
        reason = _rejected(_check(_doc(payload=payload)), HTTPStatus.BAD_REQUEST).reason
        assert "'payload'" in reason

    def test_schema_failure_still_burns_the_nonce(self) -> None:
        nonces = NonceCache()
        _rejected(_check(_doc(v=2), nonces=nonces), HTTPStatus.BAD_REQUEST)
        _rejected(_check(_doc(), nonces=nonces), HTTPStatus.CONFLICT)
