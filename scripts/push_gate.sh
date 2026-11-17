#!/bin/bash

# ============================================================================
# pre-push gate for an UN-stamped tree: pre-commit plus ONLY the tests the
# change since the last fully green run can affect (scripts/gate_select.py),
# with the 100% line bar on the changed dart files. Budget: 60 s wall-clock.
#
# Never narrows silently: it prints which tests ran and why, and refuses
# (exit 1) when the selection is the full suite or exceeds the budget -- those
# belong to scripts/full_gate.sh, which stamps the tree.
#
#   push_gate.sh [BASE]     BASE defaults to the last full-green commit
#                           ($GIT_DIR/gate-full-green), else origin/main
# ============================================================================

set -euo pipefail

readonly APP="stronglift_replacement/workout_app"
readonly MAX_DART_TESTS="${GATE_MAX_DART_TESTS:-25}"
readonly FLUTTER_CONCURRENCY="${FLUTTER_TEST_CONCURRENCY:-2}"

die() {
    echo "push-gate: $*" >&2
    exit 1
}

cd "$(git rev-parse --show-toplevel)"
gitdir="$(git rev-parse --git-dir)"

# A red nightly/full run refuses every push until a full run is green again.
if [[ "$(cat "$gitdir/gate-full-status" 2>/dev/null || true)" == red* ]]; then
    die "RED FULL STAMP ($(cat "$gitdir/gate-full-status")). The last full suite failed; fix it and rerun scripts/full_gate.sh -- no push until it is green."
fi

base="${1:-}"
[[ -n "$base" ]] || base="$(cat "$gitdir/gate-full-green" 2>/dev/null || true)"
[[ -n "$base" ]] || base="$(git merge-base origin/main HEAD 2>/dev/null || true)"
[[ -n "$base" ]] || die "no base (no full-green commit, no origin/main): run scripts/full_gate.sh"
git rev-parse --verify --quiet "$base^{commit}" >/dev/null || die "base $base is unknown: run scripts/full_gate.sh"

sel="$(python3 scripts/gate_select.py "$base" HEAD)"
field() { jq -r "$1" <<<"$sel"; }
echo "push-gate: base ${base:0:10}..HEAD $(git rev-parse --short HEAD)"
field '.why[] | "push-gate:   " + .'

if [[ "$(field .full_dart)" == true || "$(field .full_python)" == true ]]; then
    die "the change needs the FULL suite (see above). Run scripts/full_gate.sh, then push."
fi
mapfile -t dart < <(field '.dart[]')
mapfile -t py < <(field '.python[]')
(( ${#dart[@]} <= MAX_DART_TESTS )) \
    || die "${#dart[@]} Dart tests selected, over the ${MAX_DART_TESTS}-test push budget. Run scripts/full_gate.sh."

changed=()
mapfile -t changed < <(git diff --name-only "$base"..HEAD)
pids=() names=()
run_bg() { # name, command...
    local name="$1" log
    shift
    log="$(mktemp)"
    ( "$@" >"$log" 2>&1 ) &
    pids+=("$!") names+=("$name:$log")
}

run_bg pre-commit pre-commit run --from-ref "$base" --to-ref HEAD
if (( ${#dart[@]} > 0 )); then
    rel=("${dart[@]#"$APP"/}")
    echo "push-gate: Dart ran: ${#dart[@]} tests"
    run_bg dart bash -c "cd '$APP' && env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
        flutter test --coverage --concurrency '$FLUTTER_CONCURRENCY' ${rel[*]} \
        && cd - >/dev/null && python3 scripts/gate_changed_coverage.py '$APP/coverage/lcov.info' ${changed[*]}"
fi
if (( ${#py[@]} > 0 )); then
    echo "push-gate: Python ran: ${#py[@]} test files"
    run_bg python python3 -m pytest -o addopts="--strict-markers --strict-config -p screen_locker.tests.test_sync_fixtures" \
        -p no:sugar --no-cov -q --tb=short "${py[@]}"
fi
if [[ "$(field .web)" == true ]]; then
    echo "push-gate: web ran: vitest coverage"
    run_bg web pnpm --dir web run coverage
fi

fail=0
for i in "${!pids[@]}"; do
    name="${names[$i]%%:*}" log="${names[$i]#*:}"
    if wait "${pids[$i]}"; then
        echo "push-gate: $name OK"
    else
        echo "push-gate: $name FAILED" >&2
        tail -25 "$log" >&2
        fail=1
    fi
    rm -f "$log"
done
(( fail == 0 )) || die "failed (selection above); fix it, or run scripts/full_gate.sh"
echo "push-gate: OK (selective; the full suite is the nightly's job)"
