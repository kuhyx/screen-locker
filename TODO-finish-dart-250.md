# Finish TODO — the last 10 Dart files over 250 lines

> **This file is a ready-to-use prompt.** Open this repo and say
> "do todo_finish_dart_250_prompt". It is self-contained.
> Generated 2026-08-15 at the end of a session that took the repo from 41
> files over the cap to 10. All 10 remaining are Dart.

## Goal

`bash ~/utils/scripts/check_file_length.sh --all` from the repo root exits 0.

Everything else in `refactor_claude_todo.md` still applies (no gaming the cap,
no deleting tests, no suppressions). This file only adds what the previous
session learned the hard way.

## Start here (do this first, it costs one command)

```bash
cd ~/screen-locker/stronglift_replacement/workout_app
env -u GIT_DIR flutter test 2>&1 | tail -1     # MUST print: +402: All tests passed!
```

**402 is the invariant.** Dart has no glob-parametrized test like the Python
side's `test_no_popup_widgets`, so the count never legitimately changes. Any
other number means a lost, duplicated, or non-compiling test — stop and fix
before continuing. A file that fails to *load* shows as
`Failing tests: ... loading X` and drops the count, so check the number, not
just the absence of red.

Never use `git stash` (blocked by a hook). To compare against HEAD:
`git worktree add --detach /tmp/wt HEAD` … `git worktree remove /tmp/wt`.

## The 10 files

| lines | file |
| ----: | :--- |
| 740 | `test/services/workout_sync_service_test.dart` |
| 633 | `lib/screens/workout_screen.dart` |
| 503 | `lib/screens/settings_screen.dart` |
| 426 | `test/services/progression_sync_service_test.dart` |
| 386 | `test/screens/history_screen_test.dart` |
| 383 | `test/screens/home_screen_test.dart` |
| 362 | `test/screens/workout_screen_test.dart` |
| 322 | `lib/services/workout_sync_service.dart` |
| 313 | `lib/screens/manual_workout_screen.dart` |
| 260 | `lib/screens/home_screen.dart` |

Re-run `python3 scripts/refresh_refactor_todo.py` for the live set.

## Part 1 — the 4 test files

`scripts/split_dart_test.py` works and is committed. Usage:

```bash
python3 scripts/split_dart_test.py <file> <out1>:<boundaryIdx> [<out2>:<idx> ...]
```

Boundary indices are positions in the list of top-level `group(` /
`testWidgets(` / `test(` lines. Each output takes `boundaries[idx:next_idx]`;
the source keeps everything before the first.

**Its working envelope — stay inside it:**

1. **One pass, from the pristine file.** Specify every output up front. Do NOT
   split an already-split file: indices are recomputed against the new file and
   the trailer is re-copied, which is how content went missing last time.
2. **Zero top-level declarations after `main()`.** Check with:
   `awk -v m=$(grep -n '^void main(' F | cut -d: -f1) 'NR>m && /^[A-Za-z_]/' F`
   The splitter copies the trailer, but the detection is unreliable when
   helpers sit *between* groups.
3. **No local function declarations in the preamble.** `history_screen_test.dart`
   defines `_pump`, `_wrap`, `_seed` as locals inside `main()`; both halves get
   the copy but the second half's references resolve wrong. This is why that
   file is still on the list.

**All 4 remaining files are OUTSIDE the envelope** (that's why they're left):

- `workout_sync_service_test.dart` — 2 post-`main` declarations
  (`_manualWorkoutSurvivalTests`, `_cutoverTests`), plus `_fakeFirebase`,
  `_manual`, `_PutCall` used across the split point.
- `home_screen_test.dart` — 4 post-`main` declarations (fake sync classes
  overriding `syncNow`).
- `progression_sync_service_test.dart` — 1 post-`main` declaration.
- `history_screen_test.dart` — the local-function preamble above.

**The fix, and it is its own committed step:** move those shared helpers and
fakes into a sibling `test/services/_sync_test_fixtures.dart` (or
`test/screens/_home_test_fixtures.dart`) and `import` it — the same shape as
`screen_locker/tests/_workout_sync_fixtures.py` on the Python side. Commit
that move, verified at 402, *before* splitting. Then the file is inside the
envelope and the splitter handles it.

**One file at a time → verify 402 → commit.** Batching means a wrong count
doesn't tell you which file caused it, and the revert tangles.

## Part 2 — the 6 `lib/` files

Two patterns are proven and committed; copy them.

**A. Private widget classes → `part` file.** Used on `history_screen`,
`settings_screen`, `home_screen`, `exercise_tile`, `github_mirror_screen`.
Dart privacy is library-scoped, so `part` keeps `_Foo` classes private —
making them public would trip `public_member_api_docs` and change the API.
A `part` also gets no `SF:` entry in lcov, so the coverage gate's
"every lib file must appear" guard has nothing new to miss.

**B. Methods → `extension` in a `part` file.** Used on `storage_service`
(5 files), `progression_sync_service` (4), `backup_service`,
`workout_sync_service`. Dart can't continue a class body across files, but an
extension in a part still reaches `_privateField`.

### Three hard constraints — each one cost a debugging cycle

1. **`setState` is `@protected`.** It cannot be called from an extension. Any
   State method that calls `setState` must stay in the class. This is the main
   blocker on `home_screen.dart` (260) and `settings_screen.dart` (503).
2. **Extension methods dispatch STATICALLY.** A method a test fake overrides
   must stay in the class. `_FakeSync extends WorkoutSyncService` overrides
   `pushManual` and `readMergedManualPayloads`; with those in an extension the
   *real* implementations ran and four manual-workout tests hung on
   `pumpAndSettle` instead of failing an assertion. Before moving any public
   method, grep: `grep -rn "extends <ClassName>" -A15 test/`.
   This is why `workout_sync_service.dart` is stuck at 322 — its public
   surface is what fakes bind to.
3. **Static members need qualifying inside an extension**:
   `BackupService._baseDir`, `ProgressionSyncService._stateToJson`. The
   analyzer catches this (`unqualified_reference_to_static_member_of_extended_type`).

### What's actually left to do in `lib/`

- `workout_screen.dart` (633) — **not yet attempted.** Check it for private
  widget classes first (pattern A); that's the cheap win.
- `manual_workout_screen.dart` (313) — not yet attempted.
- `settings_screen.dart` (503) — widgets already extracted. Going lower needs
  the ~190-line `build()` broken up: extract the SYNC / OFFLINE BACKUP list
  sections into private `StatelessWidget`s taking what they read as
  constructor params (they never call `setState`, so they're eligible). A
  previous attempt to slice them out as a raw widget-list getter produced
  unbalanced brackets — build the widget class properly, don't slice text.
- `home_screen.dart` (260, only 10 over) — same shape, one cohesive `build()`.
- `workout_sync_service.dart` (322) — see constraint 2. Only private helpers
  can move; getting under 250 means changing the public surface, which is a
  design decision, not a move. **Ask the user before doing that.**

## Verify (all of it, every batch)

```bash
cd ~/screen-locker/stronglift_replacement/workout_app
env -u GIT_DIR dart analyze lib/            # must be "No issues found!"
env -u GIT_DIR flutter test 2>&1 | tail -1  # must be +402
cd ~/screen-locker && pre-commit run        # includes the 100% Flutter coverage gate
```

`dart analyze` is a **no-op on test files** — `analysis_options.yaml` excludes
`test/**`. For those, the test count and the compile it implies are the only
signal.

## Done condition

- `bash ~/utils/scripts/check_file_length.sh --all` exits 0.
- 402 Dart tests pass; `flutter` coverage still 100%.
- `pre-commit run --all-files` passes.
- The app still runs on the phone: use the `phone-deploy` skill
  (`bash ~/.claude/scripts/phone_deploy.sh <app-dir> --shot <path>`), then
  **read the screenshot yourself** and confirm real progression data renders —
  weights and "Next: Workout A/B", not seeded defaults. That is what proves
  the `storage_service` part-extensions still resolve.

## Environment note (not your bug)

`python3 -m scripts.verify_lock_popup_safety` fails locally with
`RecoveryLoop.__init__() takes 3 positional arguments but 6 were given`.
The code matches the pinned gatelock 0.4.0; this machine has 0.5.0 installed.
Resync with `pip install -r requirements.txt`. **Do not "fix" the code to
match the installed version** — that would break CI. See the comment in
`scripts/_popup_form_check.py`.

REMOVE ME AFTER FINISH
