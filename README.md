# screen-locker

Tkinter/systemd screen locker with workout tracking, shared sick days, and
wake-alarm integration. It enforces a workout cadence by locking the screen
until a verified (RunnerUp, StrongLifts) or budgeted manual workout is logged.

## Sick days

A sick day is a date in the fleet-wide [`sickdays`](https://github.com/kuhyx/utils/tree/main/sickdays)
pool, nothing else: no budget, countdown, justification or debt. The lock
screen's **I'm sick** button (retry screen, no-phone screen and the Tue-Thu
prompt) marks today with one tap and unlocks; `sickdays add` or the phone do
the same. On a sick day the workout lock and the grace floor stand down,
wake-alarm's workday penalty is void, and shutdown is
`max(20:00, the normal ladder)` capped at 23:00 (`earned_time.resolve(...,
sick=True)`). A day marked after its daily reset is lifted to 20:00 by the
next 5-minute pass (`_sick_floor`); a workout that day still earns normally
and is paid out of that lift first, so it lands on the ladder value (e.g.
20:40), never 20:00 plus its whole reward. `install.sh` migrates the old
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
