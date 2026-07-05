# Workstream C — GitHub-sync channel for phone workout data

## Status

**Blocked on Workstream D** (2026-07-04 user decision — see "Sequencing
decision" below). No code has been written for this workstream. The design
questions below (sync pattern, repo name, scope) have been pre-decided so the
eventual implementation pass doesn't need to re-litigate them, but
implementation itself waits until Workstream D's shared CRDT transport
library exists and screen-locker adopts it.

## Context

Screen-locker currently learns about phone-side workouts (the
`phone_verified` workout type) via `PhoneVerificationMixin`
(`screen_locker/_phone_verification.py`): ADB pull of
`workout_result.json` first (`_pull_workout_app_json`, checking
`WORKOUT_APP_JSON_REMOTES` in `_constants.py`), falling back to scanning the
local /24 subnet for the phone app's HTTP server on port 8765
(`_fetch_http_workout`/`_scan_for_http_server`). Both mechanisms require the
phone and PC to be on the same network (USB or same LAN) at verification
time.

This workstream adds a GitHub-sync transport as the **primary** channel for
this specific data (the phone app pushes its `workout_result.json` to a
private GitHub repo/gist; the PC pulls from there instead of needing
same-network ADB/HTTP), with the existing ADB pull / HTTP-scan mechanism
demoted to **fallback** (kept, not removed — it still works when the phone
is plugged in or on the same LAN, and needs no internet-dependent third
party).

**Hard boundary — do not cross this:** RunnerUp/TCX verification
(`_runnerup_verification.py`) stays **ADB-only, unconditionally**. This
workstream must not touch `_runnerup_verification.py`'s trust model at all.
Per this repo's `CLAUDE.md`: *"Never log a RunnerUp workout from a user
claim. Always pull the actual TCX file from
`/sdcard/Documents/RunnerUp/` via ADB and verify it first."* GitHub-sync is
acceptable for `phone_verified` specifically because the workout **app**
(not the user) produces that JSON — it's a different trust boundary than a
GPS-verified run file. Moving *that* channel's transport does not weaken
the RunnerUp rule.

## Two existing sync patterns in the sibling repos (pick one, don't invent a third)

There are already two different GitHub-sync approaches running in
production in this user's other repos — read both before designing this
one:

1. **diet-guard's Contents-API repo sync**
   (`~/diet-guard/diet_guard/_sync.py` + `_sync_github.py` +
   `_sync_merge.py`, ~120/190/80 lines respectively). `GitHubSyncClient`
   (`_sync_github.py:38`) wraps the GitHub Contents API with
   `get_file_text(path)`, `put_file_text(path, text, message=...)`,
   `list_directory(path)` against a **private repo**
   (`SYNC_REPO_OWNER="kuhyx"`, `SYNC_REPO_NAME="diet-guard-sync"` in
   `_constants.py`), each device pushing to its own
   `devices/<device_id>/food_log.json` path, and `_sync.py` orchestrating
   pull-all → merge (`_sync_merge.merge_logs`) → re-sign → push. Auth is a
   fine-grained PAT read from `~/.config/diet_guard/sync_token` (scoped to
   just that one repo's contents).
2. **wake-alarm's Gist-based sync**
   (`~/wake-alarm/shutdown-wrapper.sh`, phone app writes to a **private
   Gist**, not a repo). Config at `~/.config/wake_alarm/gist_sync.json`
   with `token`/`gist_id`. Much simpler (single JSON blob, no per-device
   paths, no merge step) — matches wake-alarm's much simpler data shape (one
   wake-time value, not a growing log).

Screen-locker's `phone_verified` data is closer to diet-guard's shape (a
growing per-day log, multiple potential "devices" conceptually — though in
practice just one phone) than wake-alarm's (single current value). **Default
recommendation: model this on diet-guard's Contents-API pattern**, not
wake-alarm's Gist pattern — but confirm with the user before committing,
since it affects Workstream D's shared-library design too (a shared CRDT
transport library needs to pick one primitive, not support both).

## Sequencing decision (resolved)

**Decision (2026-07-04): wait for Workstream D.** Do not build this ahead of
D with throwaway code. This workstream stays blocked until
`workstream-d-shared-crdt-transport.md` is scoped, built, and screen-locker
adopts its shared CRDT transport library. When D lands, re-open this
document and build Workstream C on top of it rather than writing local
sync code first.

## Concrete scope (resolved — apply once Workstream D unblocks this)

1. New module `screen_locker/_sync_github.py` (or similar) — **but per
   the sequencing decision above, this will be built on Workstream D's
   shared Python CRDT transport library, not modeled directly on
   diet-guard's pre-CRDT `GitHubSyncClient`.** Diet-guard's Contents-API
   approach (private repo, per-device path under `devices/<device_id>/...`,
   pull-all → merge → push) is still the reference *shape* to follow for
   how screen-locker exposes/consumes the synced data — Workstream D should
   implement that shape under the hood.
2. **Repo name (decided): `screen-locker-sync`** — new private repo, not a
   reuse of an existing one, following the `diet-guard-sync` naming
   convention.
3. `PhoneVerificationMixin._verify_phone_workout` (or a new sibling method)
   tries GitHub-sync first, falls back to the existing
   ADB-pull → HTTP-scan chain unchanged.
4. **Scope (decided): includes the phone-side push.** The `workout_app`
   Flutter app (`stronglift_replacement/workout_app/`) needs a push
   mechanism added in the same effort as the PC-side client — mirroring
   diet-guard's `app/lib/services/sync_service.dart`, but built on
   Workstream D's shared Dart CRDT transport library rather than
   hand-rolled Dart sync code. Don't assume it's a small addition to the
   existing HTTP-server code in the phone app; scope it explicitly when
   this workstream is picked back up.
5. Auth: a scoped PAT, stored and read the same way diet-guard does
   (`~/.config/<app>/sync_token`, never logged, never committed).

## Open questions to resolve before coding

- Contents-API repo sync or Gist sync (see above) — user decision.
- New private repo name, or reuse an existing sync repo? — user decision.
- Does the phone app push on every workout completion, or on a timer/on
  next app open? Affects how "fresh" the PC-side pull needs to treat the
  data (staleness handling — screen-locker's phone-verification already has
  a `stale` status value in `_verify_phone_workout`'s return type; reuse
  that concept here rather than inventing a new one).
- Should GitHub-sync failures (offline, bad PAT, rate limit) silently fall
  back to ADB/HTTP, or surface as a distinct status the status view can
  show? Recommend: silent fallback for the lock-decision path (must not
  block the user from unlocking due to a sync hiccup), but the fallback
  itself should be visible somewhere (log line at minimum) for
  debuggability.

## Verification plan

1. Test the GitHub-sync client against a real (test) private repo/gist
   before wiring it into the mixin — confirm push/pull round-trips work,
   including auth-failure and rate-limit paths.
2. Confirm the existing ADB/HTTP fallback still works with the phone
   unplugged from GitHub (i.e. sync client returns nothing) — this is the
   regression risk: don't let a broken sync client silently break the
   already-working fallback path.
3. Full existing `_phone_verification.py` test suite
   (`test_phone_verification_part2/3/4.py`, `test_adb_and_phone.py`) stays
   green; add new tests for the sync-first path with the fallback mocked.
4. Manually verify end-to-end with the real phone: workout completed on
   phone → pushed to GitHub → PC pulls without ADB/same-LAN → screen
   unlocks.

## Critical files

- `screen_locker/_phone_verification.py` (integration point)
- `screen_locker/_constants.py` (`WORKOUT_APP_JSON_REMOTES`,
  `WORKOUT_HTTP_PORT` — new `SYNC_*` constants go here too)
- `stronglift_replacement/workout_app/lib/` (phone-side push, new work)
- Reference-only, do not modify: `~/diet-guard/diet_guard/_sync_github.py`,
  `_sync.py`, `_sync_merge.py`; `~/wake-alarm/shutdown-wrapper.sh`
- **Do not touch**: `screen_locker/_runnerup_verification.py`,
  `_runnerup_db.py` (hard boundary, see Context above)
