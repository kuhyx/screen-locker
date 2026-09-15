# screen-locker

Tkinter/systemd screen locker with workout tracking, sick-day management, and
wake-alarm integration. It enforces a workout cadence by locking the screen
until a RunnerUp-verified (or explicitly justified) workout is logged.

## Shutdown time

Every day starts at **20:00** (`BASE_HOUR` in `screen_locker/_shutdown_base.py`)
and bonuses push it later, capped at 23:00: the first counted workout +2h,
each further one +1h, and an accepted LeetCode submission that day +1h (flat,
read from leetcode-guard's ledger, once per day). The config is re-derived from
those sources on each new day, so nothing has to be "remembered" across reboots.

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
