"""Phone -> PC workout poke: the wire checks, pure and stdlib-only.

The binding contract is ``docs/DOCS-workout-poke-contract.md`` and its literal
fixture ``contracts/workout_poke_v1.json``. Everything here is a pure function
of its inputs (``now_ms`` is a parameter, never read from a clock), so the
shared-fixture test can feed it the fixture's bytes as-is. The HTTP plumbing
lives in :mod:`screen_locker._poke_server`, the crediting in
:mod:`screen_locker._poke_credit`.

The MAC is computed over the raw body bytes *as received*; nothing here ever
re-serializes JSON, because a Dart and a Python encoder disagree on floats and
non-ASCII escaping.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from http import HTTPStatus
import json
import logging
from typing import Final

__all__ = [
    "REPLAY_WINDOW_MS",
    "NonceCache",
    "PokeRequest",
    "Rejection",
    "check_request",
    "parse_key",
    "verify_signature",
]

PROTOCOL_VERSION: Final = 1
REPLAY_WINDOW_MS: Final = 120_000
KEY_HEX_LENGTH: Final = 64

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class PokeRequest:
    """A request that passed every contract check.

    Attributes:
        sent_at_ms: The phone's send time, epoch milliseconds.
        nonce: The request's one-time id.
        sandbox: Verify and answer, but write and credit nothing.
        record_id: The session's sync record id.
        payload: The session exactly as the phone synced it.
    """

    sent_at_ms: int
    nonce: str
    sandbox: bool
    record_id: str
    payload: dict[str, object]


@dataclass(frozen=True)
class Rejection:
    """Why a request was refused, and with which HTTP status."""

    status: HTTPStatus
    reason: str


def parse_key(text: str) -> bytes:
    """Decode the shared key file's content (64 hex chars, 32 bytes).

    Raises:
        ValueError: With a sentence saying what is wrong with the key.
    """
    stripped = text.strip()
    if len(stripped) != KEY_HEX_LENGTH:
        msg = f"key must be {KEY_HEX_LENGTH} hex characters, got {len(stripped)}"
        raise ValueError(msg)
    try:
        return bytes.fromhex(stripped)
    except ValueError as exc:
        msg = f"key is not valid hex ({exc})"
        raise ValueError(msg) from exc


def verify_signature(key: bytes, body: bytes, signature_header: str | None) -> bool:
    """True iff ``signature_header`` is hex HMAC-SHA256(key, body).

    Compared as bytes: the header arrives latin-1 decoded, and
    ``hmac.compare_digest`` raises on a non-ASCII ``str``.
    """
    if not signature_header:
        return False
    expected = hmac.new(key, body, hashlib.sha256).hexdigest().encode("ascii")
    given = signature_header.strip().lower().encode("latin-1", errors="replace")
    return hmac.compare_digest(expected, given)


class NonceCache:
    """Nonces seen inside the replay window, pruned by their ``sent_at``.

    Pruned by the request's own send time, not by when it arrived: a request
    stamped up to 120 s in the future stays acceptable until ``sent_at + 120
    s``, so its nonce must be remembered at least that long.
    """

    def __init__(self) -> None:
        """Start empty; the window is :data:`REPLAY_WINDOW_MS`."""
        self._seen: dict[str, int] = {}

    def check_and_add(self, nonce: str, sent_at_ms: int, now_ms: int) -> bool:
        """Record ``nonce``; False if it was already seen inside the window."""
        self._seen = {
            seen: sent
            for seen, sent in self._seen.items()
            if now_ms - sent <= REPLAY_WINDOW_MS
        }
        if nonce in self._seen:
            return False
        self._seen[nonce] = sent_at_ms
        return True

    def __len__(self) -> int:
        """How many nonces are remembered right now."""
        return len(self._seen)


def _is_int(value: object) -> bool:
    """An ``int`` that is not a ``bool`` (JSON ``true`` decodes to one)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _schema_error(doc: dict[str, object]) -> str | None:
    """The first missing or mistyped field after the replay checks, if any."""
    if not _is_int(doc.get("v")) or doc.get("v") != PROTOCOL_VERSION:
        return f"unsupported protocol version {doc.get('v')!r}; expected 1"
    if not isinstance(doc.get("sandbox"), bool):
        return "field 'sandbox' must be true or false"
    record_id = doc.get("record_id")
    if not isinstance(record_id, str) or not record_id:
        return "field 'record_id' must be a non-empty string"
    if not isinstance(doc.get("payload"), dict):
        return "field 'payload' must be a JSON object"
    return None


def _decode(body: bytes) -> dict[str, object] | Rejection:
    """The verified body as a JSON object, or a 400."""
    try:
        doc = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        # Signed by the key holder yet unparsable: a sender bug, not noise.
        _logger.warning("Poke body is signed but not UTF-8 JSON: %s", exc)
        return Rejection(HTTPStatus.BAD_REQUEST, f"body is not UTF-8 JSON ({exc})")
    if not isinstance(doc, dict):
        return Rejection(HTTPStatus.BAD_REQUEST, "body is not a JSON object")
    return doc


def _replay_check(
    doc: dict[str, object], nonces: NonceCache, now_ms: int
) -> tuple[int, str] | Rejection:
    """Checks 2 and 3: fresh enough (401), nonce unseen (409).

    Returns ``(sent_at_ms, nonce)``; a missing or mistyped field either check
    needs is a 400 at that point.
    """
    sent_at = doc.get("sent_at_ms")
    if not isinstance(sent_at, int) or isinstance(sent_at, bool):
        return Rejection(HTTPStatus.BAD_REQUEST, "field 'sent_at_ms' must be an int")
    if abs(now_ms - sent_at) > REPLAY_WINDOW_MS:
        return Rejection(
            HTTPStatus.UNAUTHORIZED,
            f"request is stale: sent_at_ms is {(now_ms - sent_at) / 1000:+.0f} s "
            "off the PC clock (+ = in the past), the window is 120 s; check "
            "the phone's clock",
        )
    nonce = doc.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return Rejection(HTTPStatus.BAD_REQUEST, "field 'nonce' must be a string")
    if not nonces.check_and_add(nonce, sent_at, now_ms):
        return Rejection(HTTPStatus.CONFLICT, f"nonce {nonce} was already used")
    return sent_at, nonce


def check_request(
    key: bytes,
    body: bytes,
    signature_header: str | None,
    nonces: NonceCache,
    now_ms: int,
) -> PokeRequest | Rejection:
    """Run the contract's checks in order; the first failure wins.

    1. signature -> 401, 2. ``|now - sent_at| <= 120 s`` -> 401,
    3. nonce unseen -> 409, 4. ``v == 1`` and fields present -> 400.
    JSON is parsed only after the MAC over the raw bytes matched.
    """
    if not verify_signature(key, body, signature_header):
        return Rejection(HTTPStatus.UNAUTHORIZED, "signature does not match the key")
    doc = _decode(body)
    if isinstance(doc, Rejection):
        return doc
    replay = _replay_check(doc, nonces, now_ms)
    if isinstance(replay, Rejection):
        return replay
    problem = _schema_error(doc)
    if problem is not None:
        return Rejection(HTTPStatus.BAD_REQUEST, problem)
    sent_at, nonce = replay
    payload = doc["payload"]
    return PokeRequest(
        sent_at_ms=sent_at,
        nonce=nonce,
        sandbox=doc["sandbox"] is True,
        record_id=str(doc["record_id"]),
        payload=dict(payload) if isinstance(payload, dict) else {},
    )
