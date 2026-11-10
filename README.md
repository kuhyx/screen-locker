# screen-locker

Tkinter/systemd screen locker with workout tracking, shared sick days, and
wake-alarm integration. It enforces a workout cadence by locking the screen
until a verified (RunnerUp, StrongLifts) or budgeted manual workout is logged.

## Sick days

A sick day is a date in the fleet-wide [`sickdays`](https://github.com/kuhyx/utils/tree/main/sickdays)
pool, nothing else: no budget, countdown, justification or debt. The lock
screen's **I'm sick** button (retry screen, no-phone screen and the Tue-Thu
prompt) marks today with one tap and unlocks; `sickdays add` or the phone do
the same. On a sick day the workout lock stands down,
wake-alarm's workday penalty is void, and shutdown is 20:00 plus the gaming
pay of everything credited that day, capped at 23:00
(`earned_time.sick_shutdown_from`). A day marked after its daily reset is
raised to it by the next live pass (`_sick_floor`), and every later credit
that day raises it again.

A credit landing at or after tonight's shutdown is never lost: tonight
becomes `min(23:00, the credit's own time + its reward)` (`_late_credit`). `install.sh` migrates the old
`sick_history.json` dates into the pool once (`scripts/migrate_sick_history.py`).

A sick day may *keep* lockers (`sickdays add --keep workout`). A kept workout
lock behaves exactly as on a normal day (lock, quota, relaxed-day penalty on
that date); only the 20:00 shutdown floor still applies, since it belongs to
the day, not to a locker. The one-tap button keeps nothing. The missed-alarm
penalty is void on its ring day only if `alarm` is off, and on its penalty day
only if `workout` is off. All of it goes through `_sick.stands_down_workout`.

## Shutdown time

Every day starts at **19:00** from 2026-10-01, 20:00 before it (`base_minutes()` in
`screen_locker/_shutdown_base.py`)
and bonuses push it later, capped at 23:00: the first counted workout +2h,
each further one +1h, an accepted LeetCode submission that day +1h (flat,
read from leetcode-guard's ledger, once per day), and a credited paper-book
reading session of 20+ pages / 20+ minutes +1h (flat, read from
[book-guard](https://github.com/kuhyx/book-guard)'s ledger, once per day, keyed
on when the reading ended). The config is re-derived from
those sources on each new day, so nothing has to be "remembered" across reboots.

A RunnerUp run is credited from its TCX export, found in the WebDAV drop
directory RunnerUp uploads to on this machine (`~/data/cloud/RunnerUp/`, plus
`processed/` once endurain-import has taken it) or, when a phone is adb-visible,
in `/sdcard/Documents/RunnerUp/`. The 15-minute `workout-sync.timer` scans both,
so a run finished after 20:00 pushes the hour later without the phone being
plugged in; the per-minute shutdown check then lifts the night lockdown on its
own once the hour is past "now" (digital-wellbeing's check script).

Runs and walks are credited by ONE rule, whatever the TCX sport or the
`_Walking` file-name suffix (RunnerUp's files and the workout app's alike): a
day's activities are summed, and the day counts once their distance reaches
3.5 km (5% GPS tolerance) OR their *moving* time reaches the shared duration
bar (30 min minus the hidden leeway). Moving time is the trackpoint pairs
seen within 30 s of each other and travelled at 0.5 m/s or more, so pauses,
standing still and GPS dropouts earn nothing. The reward is the usual one
workout credit per day (`runnerup_verified:<date>`); the log's `activity`
field is display only. Code: `screen_locker/_walk_tcx.py`.

**Retiring RunnerUp.** A week after the PC first credits a run recorded by the
workout app (TCX author `kuhy workout_app`), `runnerup-retire.timer` (daily, retries
until the phone is attached) backs `/sdcard/Documents/RunnerUp` up to
`~/data/cloud/RunnerUp/runnerup_phone_backup_<date>/` and uninstalls `org.runnerup.free`,
once the app's `.workout_app_import.json` matches `processed/`; no app run, no uninstall.
`python3 -m screen_locker.runnerup_retire --status` / `--dry-run` change nothing.

## MCP server (Claude Code integration)

screen-locker exposes a **read-only** MCP server (`screen_locker._mcp`) so
Claude Code and its subagents can query workout compliance and the
lock-decision state through typed tools — without shelling out to the
`screen-locker-status` CLI or opening the Tk window.

- **Read-only tools:** `get_status` (full status snapshot), `get_summary`
  (one-line i3blocks summary + `ok`/`warn`/`lock` state word), `explain_lock`
  (why the screen is / isn't locked right now), `get_flags` (the individual
  boolean lock-decision predicates for today).
- There are **no write/action tools**, by design. Nothing here logs a workout
  or mutates state — workouts are logged only from RunnerUp-verified TCX data,
  never from a caller's claim. No tool exposes the sync token or any HMAC key.

The `mcp` SDK is an optional dependency (`pip install -e '.[mcp]'`), kept out of
the CLI/systemd system-python path. One-time setup of the dedicated venv that
Claude Code spawns:

```bash
./scripts/setup_mcp.sh
```

Registration lives in the checked-in [`.mcp.json`](./.mcp.json) (project scope).
Restart Claude Code in this repo and approve the project MCP-server prompt for it
to load. Verify with `claude mcp list`.
