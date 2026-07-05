# Workstream D — Shared CRDT transport library across 4 repos

## Status

Scoping pass complete — see `workstream-d-scoping-findings.md` (2026-07-04)
for the answers to the four questions below and two sub-decisions that fell
out of it. Still not implemented; those sub-decisions need a user call
before any code is written. Split out from the original status-view plan
(`~/.claude/plans/screen-locker-status-streamed-feigenbaum.md`, Workstream A).
The plan is explicit: **"Scope and spec this as its own dedicated task
before writing any code — do not start it opportunistically inside
Workstream A/B/C work."** This document is orientation for that future
scoping pass, not a spec to start coding from.

## The decision this workstream implements

Per explicit prior user decision: build a shared **Python** CRDT transport
library (used by screen-locker, diet-guard, wake-alarm PC-sides) and a
shared **Dart** CRDT transport library (used by todo, diet-guard app,
wake-alarm `phone_app`, screen-locker's `workout_app`), with **all four
apps adopting CRDT-based merge** — not just todo's existing use of it. This
was flagged during the original planning conversation as more complexity
than diet-guard/wake-alarm/screen-locker's simpler log data strictly needs,
and the user chose it anyway as a deliberate future-proofing call. That
tradeoff decision stands; this document doesn't re-litigate it, only
records what's actually true about the current state so a future scoping
pass starts from facts, not assumptions.

## What's actually true today (verified by reading the code, not assumed)

**todo's "CRDT approach" is the `sqlite_crdt` package**, not hand-rolled
logic: `todo/lib/sync/sync_service.dart` imports
`package:sqlite_crdt/sqlite_crdt.dart` and syncs by "pulling every other
device's full CRDT changeset" (per that file's own doc comment) — merge
conflict resolution is handled entirely inside that library, not in
app code. This matters: Workstream D's Dart-side library is not "extract
what todo already built," it's "wrap/standardize how todo already uses a
third-party package," which is a smaller and clearer task than a
from-scratch CRDT implementation.

**diet-guard and wake-alarm do NOT use CRDTs today.** Their existing
"merge" mechanisms are much simpler:
- diet-guard: `_sync_merge.merge_logs` (`~/diet-guard/diet_guard/_sync_merge.py`,
  81 lines) is a tombstone-aware, entry-key-based merge — closer to
  last-write-wins per entry than a general CRDT. Transport is
  `_sync_github.GitHubSyncClient` against a private repo's Contents API
  (see Workstream C's doc for the concrete interface).
- wake-alarm: `shutdown-wrapper.sh` reads a **private GitHub Gist**
  directly in bash — no merge logic at all, because it's a single current
  value (next wake time), not a growing log. This is the piece the
  original plan flags as needing a rewrite ("wake-alarm's current
  bash-based PC-side gist reader... into something that can participate in
  a CRDT merge") — but note its data model (one current value, no history)
  may not even need CRDT semantics; forcing it into the same abstraction
  as diet-guard's growing log is itself a design choice to confirm, not a
  given.

**No existing Python CRDT-backed storage layer exists in any of these
repos.** Unlike the Dart side (where `sqlite_crdt` is a mature, adopted
package), the Python PC-side transport library has no equivalent starting
point. This is the biggest unknown in scoping this workstream: does a
suitable Python CRDT library exist and fit sqlite/JSON-log use cases, or
does "shared Python CRDT transport library" mean writing CRDT merge logic
from scratch in Python? That question needs an answer before any
time/complexity estimate for this workstream means anything.

## Why this is a separate, large task (not a natural extension of A/B/C)

- Spans 4 repositories (todo, diet-guard, wake-alarm, screen-locker) and 2
  languages (Dart, Python).
- Touches production sync code in apps that are already shipping and
  working (diet-guard's Contents-API sync, wake-alarm's Gist reader) —
  regressions here have real user-facing consequences (diet-guard's own
  memory notes record a prior 3-day silent outage from a similar
  deployment-path mismatch — see
  `feedback-verify-real-deployment-path.md` in this user's memory).
- Requires picking one canonical transport primitive (Gist vs. Contents-API
  repo, per Workstream C's open question) that all four apps then share —
  a decision this document deliberately does not make, since it depends on
  Workstream C's resolution.
- The Python-side CRDT gap (previous section) may turn "build a shared
  library" into "evaluate/adopt a third-party Python CRDT library" or
  "design a minimal CRDT scheme from scratch" — materially different
  scopes that need to be distinguished before estimating.

## Scoping pass — what actually needs to happen before coding starts

This is not an implementation plan. Before any code is written for this
workstream, produce (as a separate, dedicated planning task):

1. **Python CRDT landscape check**: does a maintained Python package exist
   that plays well with SQLite or flat JSON logs (the data shapes
   diet-guard/wake-alarm/screen-locker actually use today)? If none fits,
   decide: adopt something not-quite-right, or hand-roll a minimal
   CRDT (e.g. a simple LWW-register or OR-set scheme, since the data here
   is genuinely simple — daily log entries, not concurrent rich-text
   editing).
2. **Transport primitive decision**: Gist vs. Contents-API repo (see
   Workstream C) — must be settled first since the shared library wraps
   whichever one is chosen, for all 4 apps, not per-app.
3. **Per-app migration cost, assessed individually**:
   - todo: likely smallest — already on `sqlite_crdt`, mainly a question of
     whether it also needs to move onto the shared library's transport
     wrapper, or keeps its current transport untouched.
   - diet-guard: rewrite `_sync_merge.py`'s tombstone-LWW merge onto a real
     CRDT scheme, both Python (`_sync.py`) and Dart
     (`app/lib/services/sync_merge.dart`) sides.
   - wake-alarm: full rewrite of `shutdown-wrapper.sh`'s bash Gist reader
     into something CRDT-capable — the single biggest unknown, since it's
     currently the simplest and most different data model of the four
     (single value, no log, no merge today at all).
   - screen-locker: net-new — no existing sync of any kind yet
     (Workstream C is what introduces sync here at all; if C is built with
     "local, throwaway sync code" per its own doc, D's arrival means
     replacing that code, not extending it).
4. **Sequencing relative to Workstream C**: confirm whether C should be (a)
   built on local throwaway sync code now and migrated onto D's library
   later, or (b) blocked until D's library exists. This is Workstream C's
   open question too — resolve it once, here or there, not independently
   in both places.

## Explicitly out of scope for the scoping pass itself

Do not write any CRDT library code, do not touch any of the 4 repos'
existing sync mechanisms, and do not commit to the Python-CRDT-library
question's answer without actually researching current (as of when this
task is picked up) Python package options — the answer may be stale by the
time this is scoped for real.

## Critical files (reference only — read, do not modify, during scoping)

- `~/todo/lib/sync/sync_service.dart`, `sync_settings.dart` (CRDT-via-package pattern)
- `~/diet-guard/diet_guard/_sync.py`, `_sync_github.py`, `_sync_merge.py`
- `~/diet-guard/app/lib/services/sync_service.dart`, `sync_merge.dart`
- `~/wake-alarm/shutdown-wrapper.sh`
- `docs/todo/workstream-c-github-sync-workout-data.md` (this repo — resolve
  its open questions jointly with this one, not independently)
