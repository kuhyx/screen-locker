do NOT run tests unless specifically instructed to do so or before committing
If tests fail on the same issue twice in a row, STOP and ask the user how to proceed instead of continuing to fix and retry.
ALWAYS confirm that the feature you add / bug you fixed behaves as it should by running the program after your changes (not tests!) and inspecting output comparing it with what user wanted, after confirming by yourself ask user if the program behaves as they intended
After running tests fix all coverage gaps and issues, do not ignore unless specifically instructed to do so
You are NOT done until you install the new version on the phone itself:
`bash ~/.claude/scripts/phone_deploy.sh stronglift_replacement/workout_app`
(it picks a safe versionCode and launches; never a bare `flutter install`).
To drive a whole workout on the phone without touching real data, deploy the
sandbox flavor instead: `... --flavor sandbox`. That is a separate package
(`com.kuhy.workout_app.sandbox`) with its own data, no network, no LAN server,
a red SANDBOX ribbon, and a SANDBOX section in Settings (wipe, "mark today not
done", rest length in seconds). Its trace is `adb logcat -s WorkoutSandbox`.

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

## The shutdown hour is derived, never incremented into

`/etc/shutdown-schedule.conf` is recomputed from scratch by
`_shutdown_base.reset_to_base_if_new_day` on each new day:
`BASE_HOUR (19) + today's workout hours + the LeetCode hour + the reading hour`,
capped at 23.
Anything that pushes the hour with a plain read-add-write and is *not* a term
of that derivation gets wiped by the next reset -- that is how a 00:02 workout
lost its hours on 2026-09-13. Add a new bonus source as a term first, then
(optionally) as a live pass stamped in `shutdown_base.json` so the two do not
double-apply. The base is the constant, not the state file: the file once
persisted `base_*_hour`, which made the code's default dead.

The LeetCode hour is read from leetcode-guard's ledger
(`_leetcode_bonus.py`): HMAC-verified `credit` entries, keyed on LeetCode's
own `submitted_at`, flat +1h/day, and *fail closed* -- an unreadable ledger or
key earns nothing. leetcode-guard itself stays read-only; it never writes
the config.

The reading hour is the same shape, from book-guard's ledger
(`_reading_bonus.py`): HMAC-verified `credit` entries with `detail.bonus ==
"1"`, dated by `detail.ended_at` (when the reading happened, not when the quiz
was passed), flat +1h/day, fail closed. The base moves 20 -> 19 on
2026-10-01 (`base_hour()`, `READING_BASE_FROM`) -- book-guard's start date, so
the cut never lands before the hour that pays for it; the 23:00 best case is
unchanged.

## The morning session is the carrot — and the early-bird window is it

`EarlyBirdMixin._is_early_bird_time` no longer reads a clock: it is open
exactly while wake-alarm's signed file grants an exemption (before the
alarm, during the session, until 11:00 once it completed in time). The
05:00–08:30 window and the extended-to-09:00 reward locked someone who got
up at 07:00 and were a second mechanism next to the one that knows whether
the user is up (2026-09-20). The pending marker is banked by the
`wake_alarm_skip` rung; `early-bird-workout-check.timer` (09:30:30, 11:00:30)
re-checks just after the carrot's two possible ends.

The `wake_alarm_skip` rung reads wake-alarm's HMAC-signed
`~/.local/state/wake_alarm/morning_session.json` (`_morning_session.py`), not
Firebase: wake-alarm is the only reader, and the previous channel here pointed
at a path that stopped existing when the repos split and answered "no skip"
for a year without an error. The whole decision is *signature ok, dated today,
now < exempt_until*; the 09:30/11:00 cutoffs live in wake-alarm
(`DOCS-morning-session-pc.md`) and must not be re-derived here. The enforce
path waits up to 30 s for a freshly booted PC's refresher; status paths never
wait, and tests pin the retry to 0.
