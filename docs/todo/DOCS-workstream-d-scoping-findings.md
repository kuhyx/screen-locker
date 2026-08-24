# Workstream D — scoping pass findings (2026-07-04)

Answers the four scoping questions from `workstream-d-shared-crdt-transport.md`,
based on reading the actual code in all four repos (not the prior doc's
summaries) and researching current Python CRDT packages. No code was written
or modified in any repo for this pass, per that doc's explicit instruction.

## Headline finding: "shared CRDT transport library" is two separable things

The original doc bundles **transport** (how bytes move between devices) and
**merge** (how conflicting data reconciles) into one library. They turn out
to have very different shareability:

- **Transport** (GitHub Contents API client: `get_file_text` /
  `put_file_text` / `list_directory` against a private repo) is genuinely
  shared already — it's independently duplicated almost line-for-line
  between todo's `GitHubClient` and diet-guard's `GitHubSyncClient`
  (`~/diet-guard/diet_guard/_sync_github.py`, 191 lines, `requests`-only).
  Extracting this into a shared Python lib (and a shared Dart lib for
  todo's/diet-guard's Dart-side client) is low-risk, small, and is the part
  Workstream C already committed to (Contents-API pattern, not Gist —
  see `workstream-c-github-sync-workout-data.md`).
- **Merge** is *not* uniformly shareable — see next section. Treating "pick
  one CRDT scheme for all four apps" as a single decision undersells that
  todo and the other three apps are solving different problems.

Recommendation: split the library (or at least the decision) along this
seam. Extract shared transport now; treat "one unified merge scheme" as a
separate, larger, and more questionable decision (see "Sub-decisions" below).

## 1. Python CRDT landscape check

Checked PyPI for currently-maintained options (search run 2026-07-04):

| Package | Status | Fit |
|---|---|---|
| `pycrdt` | Actively maintained (0.14.1, June 2026), owned by Project Jupyter | Bindings for Yrs (Rust Yjs port). Built for rich collaborative documents (maps/arrays/text with binary Yjs encoding) — the same engine behind JupyterLab real-time collaboration. Wrong shape for this use case: output isn't git-diffable JSON, has no SQLite/flat-file integration, and models a fundamentally richer editing problem (concurrent character-level text edits) than "append a log entry, sometimes delete one." Adopting it would mean encoding every log entry into a Yjs doc and pushing an opaque binary blob to GitHub instead of the current human-readable JSON — a downgrade in debuggability for no benefit these apps need. |
| `crdts`, `python3-crdt`, `crdt-py` | No PyPI release in 12+ months each — effectively unmaintained | Implement classic primitives (G-Set, OR-Set, LWW-Element-Set, PN-Counter) which are closer in shape to what's needed, but taking on an unmaintained external dependency for a handful of well-understood, stable algorithms is a worse trade than owning the ~80 lines directly. |
| `cr-sqlite` | Actively maintained, but is a native loadable SQLite *extension*, not a Python package — usable from Python's `sqlite3` module once compiled/loaded | Would require migrating diet-guard/screen-locker/wake-alarm's storage from flat JSON files to SQLite first. None of them store data in SQLite today. That's a materially bigger, unrelated migration bundled into this workstream — out of scope unless the user wants to widen it. |

**Conclusion: no third-party package fits "CRDT over a flat, git-diffable
JSON log" well.** The pragmatic answer isn't "adopt X" or "hand-roll a CRDT
from scratch" (the doc's original framing) — it's **formalize what
diet-guard already built**. `diet_guard/_sync_merge.py`'s entry-id-keyed,
tombstone-wins merge (mirrored test-for-test in
`app/lib/services/sync_merge.dart`) already has the properties a CRDT needs
here — commutative and idempotent per its own docstring and the mirrored
Python/Dart test suites — *given one constraint*: entry bodies are never
mutated after creation, only `deleted`/`hmac` change. That's a **remove-wins
register per entry**, not a general add-wins OR-Set, and it works precisely
*because* diet-guard's and screen-locker's data is an append-only log of
otherwise-immutable entries. Extracting this ~80-line scheme into the shared
Python lib (and its Dart mirror into the shared Dart lib) is a small,
low-risk task with a working reference implementation and existing tests to
port, not new CRDT design.

## 2. Transport primitive decision

**Contents-API repo pattern**, not Gist. This was already decided for
Workstream C and this pass confirms it's the right call for the shared
library too:

- todo and diet-guard already both use a Contents-API-shaped client
  independently (private repo, `listDirectory`/`getFileText`/`putFileText`)
  — it's the de facto standard across this user's repos already, not a new
  choice.
- wake-alarm is the only Gist user, and (see sub-decision 2 below) its data
  shape doesn't need what the shared library is for in the first place.

## 3. Per-app migration cost (revised — the original doc's "todo = smallest
lift" assumption does not hold)

Checked `~/todo/lib/data/note_repository.dart`: notes are **mutated in
place** — `upsert()` does `INSERT ... ON CONFLICT DO UPDATE SET text = ?,
priority = ?, status = ?, updated_at = ?`, relying on `sqlite_crdt`'s
per-column Hybrid-Logical-Clock last-writer-wins to reconcile concurrent
edits to the *same* note's *same* fields. This is a genuinely different CRDT
problem from diet-guard's/screen-locker's append-only, immutable-once-written
log entries. A shared scheme built around diet-guard's tombstone approach
(section 1) does not cover todo's need without significant extension
(effectively re-deriving field-level LWW/HLC in the shared lib) — and
`sqlite_crdt` already solves todo's exact problem well today.

| App | Data shape | Current state | Migration cost if unified merge scheme required | Migration cost if shared transport only |
|---|---|---|---|---|
| todo | Mutable records, per-field edits | `sqlite_crdt` (HLC-based, mature, in production) | **L** — would need the shared lib to grow field-level LWW to match what it already has, i.e. reimplement `sqlite_crdt`'s core in the shared lib for no behavior gain | **S** — keep `sqlite_crdt` for merge, optionally swap its transport for the shared client |
| diet-guard | Append-only log, tombstoned deletes, immutable bodies | Hand-rolled tombstone merge (Python + Dart, mirrored) | **S** — this *is* the reference implementation to extract | **S** — same, transport already Contents-API-shaped |
| wake-alarm | Single current scalar (next wake time), single writer, no history | No merge logic at all (Gist overwrite) | **M–L** for no behavioral gain — see sub-decision 2 | **S** if just swapping Gist → Contents-API for transport consistency; **none needed** if left as-is |
| screen-locker | Append-only log (workout entries), net-new sync | Nothing exists yet | **S** — greenfield, adopts whatever the shared lib provides directly | **S** — same |

## 4. Sequencing relative to Workstream C

The prior "C waits for D" decision was made when D was "not started, not
scoped" (2026-07-04, same day). This scoping pass changes what's actually
being waited on: the *transport* piece (what C needs first — Contents-API
client) is small, low-risk, and effectively already designed by example in
diet-guard's `_sync_github.py`. The *merge-unification* question (does one
scheme cover all four apps, per sub-decision 1) is the open, larger piece —
and screen-locker's own data (an append-only workout log, same shape as
diet-guard's) doesn't actually need that question resolved first, since the
diet-guard-style tombstone scheme already fits it directly.

**Flagging, not deciding:** it may be possible to unblock Workstream C on
just the shared transport client + the diet-guard-style merge scheme,
without waiting for a resolution on whether/how todo's different merge
problem folds into the "shared" library. That's a sequencing option to
confirm with the user, not something this pass resolves unilaterally.

## Sub-decisions — resolved (2026-07-04, user call, overriding this doc's recommendations)

Both sub-decisions below were put to the user with an explicit recommendation
each way this pass leaned against; the user considered the trade-off and
decided the other way on both. Recorded here as settled, not open:

1. **One unified merge scheme, covering all four apps including todo.**
   This means the shared library's merge scheme must be extended beyond the
   diet-guard-style tombstone-log scheme to also handle todo's mutable,
   per-field-edited notes — i.e. it needs to grow something equivalent to
   `sqlite_crdt`'s per-column HLC last-writer-wins, in Python and Dart, not
   just the simpler append/tombstone case. This is materially more design
   and implementation work than the transport-only extraction (was flagged
   as **L** cost in the table above) — budget for it accordingly when this
   moves to an implementation plan.
2. **wake-alarm converts to CRDT merge too**, despite its data (single
   current wake-time value, one writer, no history) having no actual
   concurrent-edit conflict for a CRDT to resolve. This is consistency-driven
   rather than need-driven — noted so a future implementer isn't confused
   about why a single-scalar value is running through CRDT merge logic; it's
   an intentional choice, not an oversight.

Net effect on scope: this makes Workstream D closer to its original framing
(one CRDT scheme, all four apps) than the leaner split this pass initially
recommended. The Python-CRDT-landscape conclusion from section 1 still holds
regardless — no third-party package fits, so the unified scheme is still
something to build by generalizing diet-guard's approach and folding in
per-field LWW for todo/wake-alarm's single-value case, not something to pull
off the shelf.

## Critical files referenced (read-only during this pass)

- `~/todo/lib/sync/sync_service.dart`, `~/todo/lib/data/note_repository.dart`
- `~/diet-guard/diet_guard/_sync.py`, `_sync_github.py`, `_sync_merge.py`
- `~/diet-guard/app/lib/services/sync_merge.dart`
- `~/wake-alarm/shutdown-wrapper.sh`
- `docs/todo/workstream-c-github-sync-workout-data.md` (this repo)
