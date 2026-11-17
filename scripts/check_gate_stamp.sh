#!/bin/bash

# ============================================================================
# pre-push gate: is the pushed tree stamped as having passed the local gate?
#
# Thin delegate to the shared tool in ~/src/utils. The pre-push stage used to
# re-run every suite (10+ min under the resource cap); now finish_auto.sh's
# gate leaves a receipt (the tree hash) and this only compares against it.
#
# Usage:
#   scripts/check_gate_stamp.sh check   # pre-commit's pre-push stage (~1 s)
#   scripts/check_gate_stamp.sh full    # the old pre-push suites, then stamp
# ============================================================================

set -euo pipefail

readonly SHARED_GATE="${UTILS_ROOT:-$HOME/src/utils}/scripts/gate_stamp.sh"

main() {
    if [[ ! -x "$SHARED_GATE" ]]; then
        echo "Error: shared gate-stamp tool not found at $SHARED_GATE" >&2
        echo "       Clone github.com/kuhyx/utils to ~/src/utils, or set" >&2
        echo "       UTILS_ROOT to where it lives." >&2
        exit 1
    fi

    # A stamped tree (full gate green) passes in ~1 s. An unstamped tree gets
    # the selective push gate: pre-commit + only the tests the change can
    # affect, <=60 s, and it says which ran and why (scripts/push_gate.sh).
    if [[ "${1:-}" == check ]]; then
        local here
        here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        if bash "$SHARED_GATE" check 2>/dev/null; then
            exit 0
        fi
        echo "gate-stamp: tree not fully stamped; running the selective push gate" >&2
        exec bash "$here/push_gate.sh"
    fi
    exec bash "$SHARED_GATE" "$@"
}

main "$@"
