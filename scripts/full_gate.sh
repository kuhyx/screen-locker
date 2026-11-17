#!/bin/bash

# ============================================================================
# The FULL suite, outside the push path: every manual-stage hook of
# .pre-commit-config.yaml as its own <60 s step (gate_stamp.sh step <id>), then
# a green or red verdict in $GIT_DIR:
#   gate-full-green    commit the full suite passed on (push gate's base)
#   gate-full-status   "green <commit> <time>" or "red <hook-id> <commit> <time>"
# A red status makes scripts/push_gate.sh refuse every push until a full run
# is green again. The stamp itself is written by gate_stamp.sh once every
# step passed, as before.
#
#   full_gate.sh list          hook ids, one per line
#   full_gate.sh step <id>     one step (interactive use: one call each)
#   full_gate.sh all           every step in order, stops at the first red
#                              (the nightly timer's entry point)
# ============================================================================

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
gitdir="$(git rev-parse --git-dir)"
readonly GATE="bash scripts/check_gate_stamp.sh"

record() { # verdict words...
    printf '%s %s\n' "$*" "$(date -Is)" > "$gitdir/gate-full-status"
}

run_step() {
    local id="$1" head
    head="$(git rev-parse HEAD)"
    if $GATE step "$id"; then
        # The last passing step stamps the tree: that is a full green.
        if bash "${GATE_SHARED:-$HOME/src/utils/scripts/gate_stamp.sh}" check >/dev/null 2>&1; then
            printf '%s\n' "$head" > "$gitdir/gate-full-green"
            record green "$head"
            echo "full-gate: GREEN on ${head:0:10}"
        fi
    else
        record red "$id" "$head"
        echo "full-gate: RED at '$id' on ${head:0:10}; pushes are refused until green" >&2
        return 1
    fi
}

case "${1:-}" in
    list) $GATE full --list ;;
    step) run_step "${2:?usage: full_gate.sh step <hook-id>}" ;;
    all)
        while IFS= read -r id; do run_step "$id"; done < <($GATE full --list)
        ;;
    *) echo "usage: full_gate.sh list | step <id> | all" >&2; exit 2 ;;
esac
