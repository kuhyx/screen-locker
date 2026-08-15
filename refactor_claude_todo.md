# Refactor TODO — enforce the 250-line file cap

> **This file is a ready-to-use prompt.** Paste it to Claude, or open this repo
> and say "do refactor_claude_todo". It is self-contained: everything needed to
> execute is below. Generated 2026-08-14 from a measured survey of every repo.

## Goal

Every file in this repo must be **at most 250 lines** — source, tests, and
prose (`.md`/`.txt`/`.rst`/`.tex`) alike — and must **stay** that way forever,
enforced by a gate that fails the commit, not by a note anyone can ignore.

Why: a file that cannot be read in one piece forces re-reads and partial edits,
which is the single largest avoidable cost in an LLM-assisted workflow. Aim by
churn, not size alone — refactoring pays where code is read and changed often
(Fowler, _refactoring economic benefit_).

## Scope in this repo

<!-- BEGIN GENERATED VIOLATIONS -->

- **61 files** currently exceed 250 lines.
- **9,084 lines** over the cap in total (the work left to do); longest file is **897** lines.

ROI = lines x commits in the last year. Work top-down; a long file nobody edits
has near-zero payoff and should not be first.

| lines | commits/yr | kind | file |
| ----: | ---------: | :--- | :--- |
| 771 | 12 | code | `stronglift_replacement/workout_app/lib/screens/settings_screen.dart` |
| 781 | 10 | code | `stronglift_replacement/workout_app/lib/services/storage_service.dart` |
| 897 | 8 | code | `stronglift_replacement/workout_app/lib/screens/history_screen.dart` |
| 323 | 22 | code | `screen_locker/tests/conftest.py` |
| 480 | 12 | code | `stronglift_replacement/workout_app/test/screens/settings_screen_test.dart` |
| 633 | 9 | code | `stronglift_replacement/workout_app/lib/screens/workout_screen.dart` |
| 343 | 16 | code | `screen_locker/tests/test_init_and_log.py` |
| 740 | 7 | code | `stronglift_replacement/workout_app/test/services/workout_sync_service_test.dart` |
| 370 | 14 | code | `screen_locker/_ui_flows.py` |
| 380 | 13 | code | `screen_locker/_phone_verification.py` |
| 759 | 5 | code | `stronglift_replacement/workout_app/test/services/storage_service_test.dart` |
| 415 | 9 | code | `stronglift_replacement/workout_app/lib/services/workout_sync_service.dart` |
| 357 | 9 | code | `screen_locker/_manual_workout_dialog.py` |
| 384 | 8 | code | `screen_locker/_shutdown.py` |
| 383 | 8 | code | `stronglift_replacement/workout_app/lib/screens/home_screen.dart` |

_(46 further files over 250 lines not listed — re-run `python3 scripts/refresh_refactor_todo.py` for the current set.)_

<!-- END GENERATED VIOLATIONS -->


Exempt (do NOT split these):

- generated files — `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `**/l10n/generated/**`,
  anything with a `GENERATED` header
- markup — `.html`, `.css`, `.scss`
- data files — `.json`, `.yaml`, `.csv`, wordlists and other data-ish `.txt`
  (mean line length under 25 chars)


## How to split

- **Python** — extract cohesive helpers into sibling modules; keep the public
  API and imports stable.
- **Shell** — split into `lib/*.sh` sourced by a thin entry script. Keep
  `set -euo pipefail` in each.
- **Dart / TypeScript** — extract widgets/components into their own files.
- **Tests** — split by test-group into sibling files
  (`foo.test.ts` -> `foo.parsing.test.ts`, `foo.render.test.ts`). Coverage must
  not drop.
- **Docs** — split into topic files under `docs/` with an index. For an
  oversized `CLAUDE.md`, move detail into referenced docs so the
  always-loaded part shrinks.

**Do not** game the cap: no one-lining, no deleting tests, no moving code into
an exempt extension, no `# noqa`-style suppressions.

## Make it permanent (required — this is the point)

A refactor without a gate silently regrows. Before this task is done:

1. Wire the shared gate `~/utils/scripts/check_file_length.sh` into this repo's
   `.pre-commit-config.yaml` as a local hook. If the repo has no pre-commit
   config, add a minimal one.
2. The hook checks **files in the commit** (not the whole tree), so unrelated
   commits never break, and it **fails** — exit 1, not a warning.
3. No baseline file and no allowlist. Those are suppressions.
4. If this repo has CI (`.github/workflows`), add the same check there so it
   also fails on push.

## Done condition

- `bash ~/utils/scripts/check_file_length.sh --all` from this repo root exits 0.
- The repo's own test suite and coverage bar are still green.
- `pre-commit run --files <changed files>` passes.
- A deliberately over-250-line test file, staged, makes `git commit` **fail**.
- For a deployed daemon/app: the entry point still actually runs.

## Verify

Run the suite, then actually run the locker entry point — this repo deploys from the working tree, so a broken import is a live outage.
