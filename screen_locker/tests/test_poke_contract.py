"""The PC receiver against the shared phone<->PC poke fixture.

``contracts/workout_poke_v1.json`` is the literal both sides test against
(the Dart sender has the twin of this test). A drift in key decoding, body
encoding or MAC computation on this side fails here.
"""

from __future__ import annotations

from http import HTTPStatus
import json
from pathlib import Path

from screen_locker._poke_wire import (
    NonceCache,
    PokeRequest,
    Rejection,
    check_request,
    parse_key,
    verify_signature,
)

_FIXTURE = Path(__file__).resolve().parents[2] / "contracts" / "workout_poke_v1.json"


def _fixture() -> tuple[bytes, bytes, str]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    key = parse_key(data["key_hex"])
    body = data["body_utf8"].encode("utf-8")
    return key, body, data["signature_hex"]


def test_fixture_signature_verifies_over_raw_bytes() -> None:
    key, body, signature = _fixture()
    assert verify_signature(key, body, signature)


def test_one_altered_byte_is_rejected() -> None:
    key, body, signature = _fixture()
    altered = bytearray(body)
    # The '1' in "v":1 -> '2': still valid JSON, so only the MAC can catch it.
    altered[body.index(b'"v":1') + 4] = ord("2")
    assert not verify_signature(key, bytes(altered), signature)


def test_fixture_passes_every_contract_check() -> None:
    key, body, signature = _fixture()
    sent_at = json.loads(body)["sent_at_ms"]
    result = check_request(key, body, signature, NonceCache(), now_ms=sent_at)
    assert isinstance(result, PokeRequest)
    assert result.record_id == "2026-10-09T15:10:40.953"
    assert result.payload["duration_seconds"] == 7020.5
    assert result.payload["note"] == "zażółć gęślą jaźń"


def test_altered_body_is_a_401_through_check_request() -> None:
    key, body, signature = _fixture()
    altered = body.replace(b'"sandbox":false', b'"sandbox":true ')
    result = check_request(key, altered, signature, NonceCache(), now_ms=0)
    assert isinstance(result, Rejection)
    assert result.status is HTTPStatus.UNAUTHORIZED
