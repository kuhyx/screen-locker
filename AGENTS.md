do NOT run tests unless specifically instructed to do so or before committing
If tests fail on the same issue twice in a row, STOP and ask the user how to proceed instead of continuing to fix and retry.
ALWAYS confirm that the feature you add / bug you fixed behaves as it should by running the program after your changes (not tests!) and inspecting output comparing it with what user wanted, after confirming by yourself ask user if the program behaves as they intended
After running tests fix all coverage gaps and issues, do not ignore unless specifically instructed to do so
You are NOT done until you install the new version on the phone itself (flutter install --debug from the workout_app directory, then adb shell monkey -p com.kuhy.workout_app to launch).

## NEVER fail silently

A failure that says nothing is a bug. The PC's workout sync did nothing for
weeks because a missing token `return`ed `[]` and real errors only logged at
`INFO` — nobody could tell "nothing to do" from "it broke".

- **Swallowed exceptions must say why, loudly.** Every `except` must either
  re-`raise` or log at `warning`/`error`/`exception`/`critical` with the
  concrete reason. `debug`/`info` do NOT count — an invisible log is a silent
  failure with extra steps. Enforced by `scripts/check_silent_failures.py`
  (pre-commit hook `no-silent-failures`); ruff's `S110` only catches
  `except: pass`, which is the rare case.
- **Guard clauses that abort work must log too.** `if token is None: return`
  is a silent no-op. Say what was missing and what it means.
- **Return something meaningful.** Prefer a typed result (e.g.
  `_manual_push.PushResult(pushed, record_count, reason)`) over a bare
  `None`/`[]`/`False`, so the caller can react instead of guessing. `reason`
  should read like a sentence a human can act on.
- **No escape hatch** — `# noqa` is banned repo-wide. If a failure really is
  benign, log it at `warning` and move on.
