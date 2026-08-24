# Fix TODO — make pylint a perfect 10.00 gate

> **This file is a ready-to-use prompt.** Paste it to Claude, or open this repo
> and say "do todo_fix_pylint_10_prompt". It is self-contained: everything
> needed to execute is below. Generated 2026-08-15 from a measured run.

## Goal

`pylint` must score **10.00/10** on this repo, enforced by the pre-commit hook
at `--fail-under=10` — not the current `--fail-under=8.0`, which lets real
findings through as long as enough clean files dilute them.

Why the current bar is wrong: pylint's hook scores the **staged batch** as one
number. A commit touching many test files fails while the identical code
committed alongside a few clean source files passes. The score is a property of
*which files you staged*, not of the code. A 10.00 bar removes that entirely —
zero findings is zero findings regardless of batching.

## Measured starting point (2026-08-15)

Whole repo (`screen_locker/` + `scripts/`): **8.76/10**.

Findings by category, highest first:

| count | check | fixable? |
| ----: | :--- | :--- |
| 473 | `protected-access` (W0212) | no — test-inherent |
| 369 | `unused-argument` (W0613) | no — test-inherent |
| 245 | `missing-function-docstring` (C0116) | **yes** |
| 238 | `suppressed-message` (I0020) | disappears with W0212/W0613 |
| 73 | `duplicate-code` (R0801) | no — test-inherent |
| 66 | `use-implicit-booleaness-not-comparison-to-zero` (C1805) | **yes** |
| 27 | `import-outside-toplevel` (C0415) | **yes**, mostly |
| 25 | `missing-class-docstring` (C0115) | **yes** |
| 25 | `locally-disabled` (I0011) | disappears with W0212/W0613 |
| 24 | `use-implicit-booleaness-not-comparison` (C1803) | **yes** |
| 10 | `useless-suppression` (I0021) | **yes** — delete the dead disables |
| ~40 | long tail (see "Long tail" below) | **yes** |

## The decision already taken

Three checks are **disabled for test paths only**, because they are not defects
— they are how pytest works, and fixing them would mean rewriting ~840 call
sites and making production APIs public to suit tests:

- **`protected-access` (W0212)** — tests drive private mixin methods directly
  (`locker._verify_phone_workout()`). This is deliberate: those methods *are*
  the unit under test. Ruff already exempts the same thing in tests via
  `SLF001` in `pyproject.toml`'s per-file-ignores, so pylint disagreeing with
  ruff is just noise.
- **`unused-argument` (W0613)** — pytest fixtures such as `mock_tk` and
  `mock_sys_exit` must be *requested* in the signature to take effect, but are
  never referenced in the body. Consuming them with a dummy `assert` to satisfy
  a linter is strictly worse code.
- **`duplicate-code` (R0801)** — near-identical `with patch(...)` preambles
  across sibling test modules. Deduplicating them into helpers hurts: a test
  should read top-to-bottom without chasing a shared fixture.

Everything else gets **fixed for real**. No `# pylint: disable=` lines, no
per-line suppressions — this repo bans `# noqa` / `# type: ignore` repo-wide and
the same spirit applies here.

## Steps

1. **Scope the three disables to tests only.** They must NOT apply to
   `screen_locker/*.py` or `scripts/*.py`. pylint has no per-path `disable` in
   `pyproject.toml`, so use one of:
   - a `screen_locker/tests/.pylintrc` that inherits and adds the disables
     (pylint picks the nearest rcfile per directory), or
   - two pre-commit hooks (`pylint-src` with `exclude: ^screen_locker/tests/`,
     `pylint-tests` with `files: ^screen_locker/tests/`), each `--fail-under=10`.

   Verify the scoping works: introduce a deliberate `protected-access` in a
   *source* file and confirm it still fails.

2. **Fix `missing-function-docstring` / `missing-class-docstring` (270).**
   Docstrings must say what the test *pins down*, not restate its name.
   Good: `"""An unsigned entry is rejected once a key is available."""`
   Bad: `"""Test rejected when key available."""`
   A generator that drafts from the test name lives at
   `/tmp/.../scratchpad/add_docstrings.py` in the session that wrote this file;
   it is refactor tooling, not a deliverable — rewrite it if it is gone. Every
   generated line still needs reading: the draft is a starting point.

3. **Fix the booleanness checks (94).** `assert x == []` → `assert not x`,
   `assert n == 0` → `assert not n`, `assert s == ""` → `assert not s`.
   Careful: only where the value really is a sequence/int/str. `is False` /
   `is True` assertions on tri-state returns must NOT be collapsed.

4. **Fix `import-outside-toplevel` (27).** Hoist each to module scope unless it
   exists to break an import cycle — where it does, that is a real constraint;
   restructure the modules so the cycle is gone, or leave it and note why.

5. **Delete `useless-suppression` (10)** — dead `# pylint: disable=` comments
   that no longer suppress anything.

6. **Long tail (~40).** `too-many-instance-attributes`, `too-many-arguments`,
   `too-many-return-statements`, `unspecified-encoding`, `line-too-long`,
   `comparison-with-callable`, `superfluous-parens`,
   `pointless-string-statement`, `reimported`, `consider-using-with`,
   `unreachable`. Fix each on its merits.
   - `unspecified-encoding` (3) is a genuine latent bug — add `encoding="utf-8"`.
   - `comparison-with-callable` (3) is often a real bug (comparing a function
     instead of calling it). Read each one carefully.
   - `unreachable` (4) is `sys.exit(0)` followed by `return` in
     `_startup_checks.py` and elsewhere. Those `return`s are **load-bearing
     under test**: `conftest.py` patches `sys.exit` to a no-op, so without the
     `return` execution continues into the next branch. Do not delete them
     blindly — restructure so the intent is expressed without dead code, or
     leave them and record the reason.
   - `too-many-ancestors` (1) is `ScreenLocker`'s 19 mixins. Inherent to the
     design; raise `max-parents` in config rather than collapsing mixins.

7. **Flip the gate.** Set `--fail-under=10` in `.pre-commit-config.yaml` (both
   hooks if you split them) and update the hook `name:` to say 10.

## Done condition

- `pylint --rcfile=pyproject.toml screen_locker/ scripts/` prints
  **`rated at 10.00/10`**.
- `pre-commit run --all-files` passes.
- A deliberately-introduced pylint finding in a **source** file makes
  `git commit` fail (proves the gate is live and correctly scoped).
- `python -m pytest` still green at `fail_under = 100` branch coverage.
- No `# pylint: disable=` added anywhere as part of this work.

## Verify

Run the suite, then actually run the locker entry point —
`python -m screen_locker.screen_lock --status` — because this repo deploys from
the working tree, so a broken import is a live outage. Hoisting imports (step 4)
is exactly the change that can cause one.

## Do not

- Do not lower `--fail-under` below 10 once it is raised.
- Do not add per-line `# pylint: disable=` comments to reach the number.
- Do not disable W0212/W0613/R0801 globally — tests only. A source file calling
  another class's private attribute is a real finding.
- Do not touch `refactor_claude_todo.md`'s 250-line work; that is a separate,
  in-progress task with its own prompt file.

REMOVE ME AFTER FINISH
