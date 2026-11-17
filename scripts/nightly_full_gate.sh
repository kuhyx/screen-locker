#!/bin/bash

# ============================================================================
# Nightly entry point (full-gate.timer, 22:00): run the full suite on a clean
# detached checkout of main in a throwaway worktree, unless the machine is
# busy. A red result lands in the repo's $GIT_DIR/gate-full-status, which
# refuses the next push (scripts/push_gate.sh).
# Loadavg guard: skip (exit 0, logged) when the 5-min load exceeds MAX_LOAD.
# ============================================================================

set -euo pipefail

readonly REPO="${SCREEN_LOCKER_REPO:-$HOME/src/screen-locker}"
readonly MAX_LOAD="${GATE_MAX_LOAD:-6}"

read -r _ load5 _ < /proc/loadavg
if awk -v l="$load5" -v m="$MAX_LOAD" 'BEGIN { exit !(l > m) }'; then
    echo "nightly-full-gate: load5=$load5 > $MAX_LOAD, skipped tonight" >&2
    exit 0
fi

cd "$REPO"
# The verdict files live in the main repo's git dir; the suite runs on HEAD.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "nightly-full-gate: working tree dirty, skipped (the gate stamps HEAD only)" >&2
    exit 0
fi
exec bash scripts/full_gate.sh all
