# Design audit — screen-locker

Generated against safe-design-rules (anthonyhobday.com/sideprojects/saferules).
Report only — nothing in this repo was changed by the audit itself.

This repo has two UI surfaces, audited separately below. `~/utils/gatelock`
was checked with `git -C ~/utils/gatelock rev-parse --show-toplevel` → prints
`/home/kuhy/utils`, i.e. gatelock is a subdirectory of the `~/utils` monorepo,
**not its own git repo**. Per audit scope, no separate gatelock report was
written; see the "Shared gatelock library" section at the end instead.

Split into one file per audited surface to stay under the repo's 250-line
cap; the findings themselves are unchanged.

## Sections

- [Python/Tkinter lock UI](docs/design-audit/python-tkinter-lock-ui.md) — `screen_locker/`
- [Flutter workout app](docs/design-audit/flutter-workout-app.md) — `stronglift_replacement/workout_app/`
- [Shared gatelock library](docs/design-audit/shared-gatelock-library.md) — `~/utils/gatelock`
