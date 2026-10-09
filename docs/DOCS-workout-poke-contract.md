# Workout poke: phone -> PC wire contract (v1)

The phone sends a finished StrongLifts session straight to the PC over the
home LAN, so the credit (shutdown time, gaming budget, notification) lands in
under a second instead of waiting for the GitHub/Firebase round trip. The
normal sync push still runs in parallel; the PC dedups by record id, so a
session that arrives both ways is credited once.

## Transport

- `POST http://<pc-host>:8773/v1/workout`, `Content-Type: application/json`.
- `<pc-host>` is a phone setting, default `192.168.1.43` (static on the PC).
  LAN only: the PC firewall accepts tcp/8773 from `192.168.1.0/24` and nothing
  else. No WireGuard. Off the home LAN the poke fails fast and the regular
  sync is the only path.
- Header `X-Poke-Signature: <hex HMAC-SHA256(key, raw body bytes)>`.
  The PC verifies the MAC over the bytes **as received** and only then parses
  them. Neither side may re-serialize JSON to compute or check the MAC.
- Key: 32 random bytes, hex, PC copy at `~/.config/workout_poke/key`
  (mode 600); phone copy in the Android keystore, put there by
  `scripts/pair_phone.sh` over adb.

## Request body

```json
{"v":1,"sent_at_ms":<int epoch ms>,"nonce":"<uuid4>","sandbox":<bool>,
 "record_id":"<sync record id>","payload":{<session exactly as synced>}}
```

- `payload` is the same map the phone puts in its sync log for the session;
  the PC feeds `(record_id, payload)` to `ingest_session_records`, which
  re-validates it (never trusts `succeeded`).
- `sandbox` is inside the signed body. A sandbox request is verified, timed
  and answered, but **never written anywhere** and never credited.

## PC checks, in order (each rejection is logged at warning)

1. Signature matches -> else `401`.
2. `|now - sent_at_ms| <= 120 s` -> else `401` (replay window).
3. `nonce` not seen within the window -> else `409`.
4. `v == 1` and fields present -> else `400`.

## Response (always JSON)

```json
{"ok":<bool>,"credited":<bool>,"duplicate":<bool>,"sandbox":<bool>,
 "shutdown":"HH:MM"|null,"gaming_budget_minutes":<int|null>,"pc_ms":<int>,
 "reason":"<sentence a human can act on>"}
```

The phone must treat `shutdown` and `gaming_budget_minutes` as nullable.

Outcomes of a verified (200) request:

| case | ok | credited | duplicate |
|---|---|---|---|
| newly credited | true | true | false |
| already in `log.json` (e.g. the sync got there first) | true | false | true |
| logged, but today's credit slot was already paid by another copy of the same workout | true | false | false |
| signed but does not count (too short, no date): `reason` says why | false | false | false |
| sandbox | true | false | false |

Refusals are never 200. Besides the four checks above, the PC may answer
`404` (wrong path), `405` (not POST), `411` (no Content-Length), `413` (body
over 64 KiB) and `500` (internal error; the regular sync still credits). All
of them carry the same JSON shape with `ok:false` and `shutdown` and
`gaming_budget_minutes` both `null`. The PC answers a `413` without reading
the body, so the phone may see a connection reset instead of the reply.

## Shared fixture

`contracts/workout_poke_v1.json` holds a literal key, body and expected
signature (with a float and non-ASCII text, the usual cross-language traps).
The Python receiver and the Dart sender both test against it, so a drift on
either side fails that side's tests.
