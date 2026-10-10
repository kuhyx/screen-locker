#!/usr/bin/env python3
"""Drive the running workout poke listener from this PC, signed with the real key.

Each case POSTs to ``http://127.0.0.1:8774/v1/workout`` exactly as the phone
would (``docs/DOCS-workout-poke-contract.md``) and prints the status and reply:

* ``sandbox``   -- a signed sandbox request: 200, ok, credited=false;
* ``badsig``    -- a signature for different bytes: 401;
* ``replay``    -- the same nonce twice: 200 (sandbox), then 409;
* ``stale``     -- ``sent_at_ms`` 10 minutes old: 401;
* ``duplicate`` -- a NON-sandbox poke of today's already-logged session
  (record ``2026-10-09T15:10:40.953``): duplicate=true, credited=false;
* ``latency``   -- N sandbox round trips, p50/p95 in ms.

Usage: ``python3 scripts/poke_selftest.py CASE [--count N] [--port P]``.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import json
from pathlib import Path
import statistics
import sys
import time
import uuid

KEY_FILE = Path.home() / ".config" / "workout_poke" / "key"
STALE_MS = 600_000
DUPLICATE_RECORD_ID = "2026-10-09T15:10:40.953"
# The session as the phone syncs it (same shape as the shared fixture).
DUPLICATE_PAYLOAD: dict[str, object] = {
    "date": "2026-10-09",
    "start_time": DUPLICATE_RECORD_ID,
    "workout_type": "A",
    "duration_seconds": 7020.5,
    "succeeded": True,
    "exercises": [{"name": "Squat", "weight_kg": 100.0, "sets": [5, 5, 5, 5, 5]}],
}


def _body(
    *, sandbox: bool, sent_at_ms: int | None = None, nonce: str | None = None
) -> bytes:
    """One request body; compact separators like the phone's encoder."""
    doc = {
        "v": 1,
        "sent_at_ms": sent_at_ms
        if sent_at_ms is not None
        else time.time_ns() // 1_000_000,
        "nonce": nonce or str(uuid.uuid4()),
        "sandbox": sandbox,
        "record_id": DUPLICATE_RECORD_ID,
        "payload": DUPLICATE_PAYLOAD,
    }
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _post(
    port: int, key: bytes, body: bytes, *, sign_over: bytes | None = None
) -> tuple[int, dict[str, object], float]:
    """POST ``body``, signed over ``sign_over`` (default: itself).

    Returns (status, reply, round-trip ms).
    """
    signature = hmac.new(
        key, sign_over if sign_over is not None else body, hashlib.sha256
    ).hexdigest()
    started = time.perf_counter()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(
            "POST",
            "/v1/workout",
            body=body,
            headers={"Content-Type": "application/json", "X-Poke-Signature": signature},
        )
        response = conn.getresponse()
        reply = json.loads(response.read())
    finally:
        conn.close()
    return response.status, reply, (time.perf_counter() - started) * 1000


def _show(label: str, result: tuple[int, dict[str, object], float]) -> int:
    status, reply, ms = result
    shown = json.dumps(reply, ensure_ascii=False)
    sys.stdout.write(f"{label}: HTTP {status} rtt={ms:.1f}ms {shown}\n")
    return status


def _latency(port: int, key: bytes, count: int) -> None:
    rtts = sorted(_post(port, key, _body(sandbox=True))[2] for _ in range(count))
    p95 = rtts[max(0, round(0.95 * count) - 1)]
    p50 = statistics.median(rtts)
    sys.stdout.write(
        f"latency over {count} sandbox pokes: p50={p50:.1f}ms "
        f"p95={p95:.1f}ms max={rtts[-1]:.1f}ms\n"
    )


def main() -> int:
    """Run one case against the local listener."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "case", choices=["sandbox", "badsig", "replay", "stale", "duplicate", "latency"]
    )
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--port", type=int, default=8774)
    args = parser.parse_args()
    key = bytes.fromhex(KEY_FILE.read_text(encoding="ascii").strip())
    if args.case == "sandbox":
        _show("sandbox", _post(args.port, key, _body(sandbox=True)))
    elif args.case == "badsig":
        _show(
            "badsig",
            _post(args.port, key, _body(sandbox=True), sign_over=b"something else"),
        )
    elif args.case == "replay":
        body = _body(sandbox=True)
        _show("replay first", _post(args.port, key, body))
        _show("replay again", _post(args.port, key, body))
    elif args.case == "stale":
        stale = time.time_ns() // 1_000_000 - STALE_MS
        _show("stale", _post(args.port, key, _body(sandbox=True, sent_at_ms=stale)))
    elif args.case == "duplicate":
        _show("duplicate (NON-sandbox)", _post(args.port, key, _body(sandbox=False)))
    else:
        _latency(args.port, key, args.count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
