"""Read-only MCP (Model Context Protocol) server for screen-locker.

Exposes the locker's *read-only* status surface as typed MCP tools, so an MCP
client (Claude Code and its subagents) can query today's/this week's workout
compliance, the shutdown projection, and the lock-decision trace without
shelling out to the ``screen-locker-status`` CLI or opening the Tk window.

Run via the dedicated venv that has the ``mcp`` extra installed::

    ~/.venvs/screen-locker-mcp/bin/python -m screen_locker._mcp

(see ``scripts/setup_mcp.sh`` and the repo-root ``.mcp.json``).

Safety invariants (do not break when adding tools):
  * **READ-ONLY.** There are no write/action tools here, by design. In
    particular there is deliberately **no** ``log_workout`` and no tool that
    mutates workout/compliance state — the project rule is that workouts are
    logged only from RunnerUp-verified TCX data, never from a caller's claim.
    Every tool below calls only side-effect-free leaf helpers that *read*
    on-disk state (``gather_status`` and the ``_compliance_state`` predicates),
    never a mutating CLI/daemon entry point.
  * **stdout is the JSON-RPC channel.** This module and every function a tool
    calls must never write to stdout. All logging is routed to STDERR below,
    and no tool calls ``screen_lock.py`` / ``status_view.main`` (which
    ``print`` / open Tk windows / ``sys.exit``).
  * **No secret ever leaves.** No tool returns the sync token
    (``~/.config/screen_locker/sync_token``) or any HMAC key; the predicates
    load only status/state and return booleans, and the status snapshot
    carries no secret material.
"""

from __future__ import annotations

from dataclasses import asdict
import logging
from pathlib import Path
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from screen_locker._compliance_state import (
    has_logged_today,
    is_early_bird_pending,
    is_scheduled_skip_today,
    is_sick_day_today,
)
from screen_locker._constants import (
    EARLY_BIRD_PENDING_FILE,
    SCHEDULED_SKIPS_FILE,
)
from screen_locker._sick_tracker import load_history
from screen_locker._status_data import format_summary_line, gather_status
from screen_locker.status_view import _compliance_state_word

# Log to STDERR only — STDOUT carries the MCP JSON-RPC protocol frames, so a
# single stray stdout write would corrupt the stream and kill the session.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] screen-locker-mcp: %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("screen-locker")

# The workout log lives beside the package, same default as
# ``_status_data._DEFAULT_LOG_FILE``; declared here to avoid importing a
# private name across modules.
_LOG_FILE = Path(__file__).resolve().parent / "workout_log.json"


# ──────────────────────────────────────────────────────────────
# Read tools (state-only; never expose secrets, never mutate)
# ──────────────────────────────────────────────────────────────


@mcp.tool()
def get_status() -> dict[str, Any]:
    """Return the full read-only status snapshot.

    A JSON-friendly projection of ``gather_status()``: today's and this week's
    workout outcomes, the shutdown-time projection, the lock-decision trace,
    and the rolling sick-day / manual-workout budgets. Reads on-disk state
    only (no ADB, sudo, or network) and never mutates anything.
    """
    return asdict(gather_status())


@mcp.tool()
def get_summary() -> dict[str, Any]:
    """Return the one-line i3blocks summary plus the compliance-state word.

    ``summary_line`` is the same string the status bar shows
    (``format_summary_line``); ``compliance_state`` is one of ``ok`` / ``warn``
    / ``lock`` (``_compliance_state_word``).
    """
    snapshot = gather_status()
    return {
        "summary_line": format_summary_line(snapshot),
        "compliance_state": _compliance_state_word(snapshot),
    }


@mcp.tool()
def explain_lock() -> dict[str, Any]:
    """Return why the screen is or is not being locked right now.

    A JSON-friendly projection of the ``LockExplanation`` reconstruction of the
    lock-decision chain (which skip condition fired, the full ordered trace,
    and any pending auto-upgrade opportunity). Read-only: the heat-skip stage
    is reported as not-evaluated rather than triggering a live ``wttr.in`` call.
    """
    return asdict(gather_status().lock_explanation)


@mcp.tool()
def get_flags() -> dict[str, bool]:
    """Return the individual boolean lock-decision predicates for today.

    Each predicate reads its own on-disk state file and degrades to ``False``
    when that file is missing or unreadable — none of them mutate state or
    expose secrets.
    """
    history = load_history()
    return {
        "has_logged_today": has_logged_today(_LOG_FILE),
        "is_scheduled_skip_today": is_scheduled_skip_today(SCHEDULED_SKIPS_FILE),
        "is_early_bird_pending": is_early_bird_pending(EARLY_BIRD_PENDING_FILE),
        "is_sick_day_today": is_sick_day_today(history),
    }


def main() -> None:
    """Run the MCP server over stdio (STDOUT = JSON-RPC, STDERR = logs)."""
    logger.info("Starting screen-locker MCP server (python=%s)", sys.executable)
    mcp.run()  # pragma: no cover


if __name__ == "__main__":
    main()
