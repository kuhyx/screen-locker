#!/bin/bash
# ============================================================================
# ci_mirror.sh — run the exact CI gates locally before a push can leave.
#
# Why: the installed pre-commit hook only checks *staged* files, and the local
# dev environment already has every dependency installed. CI does neither — it
# runs `pre-commit run --all-files` and installs a fresh environment from
# requirements.txt. That gap is why green-locally repos went red in CI
# (missing runtime deps, --all-files lint debt, order-dependent test flakes).
#
# This script reproduces both CI workflows on the developer machine:
#   1. a venv built ONLY from requirements.txt (mirrors the Tests workflow's
#      `pip install -r requirements.txt`), rebuilt only when requirements.txt
#      changes (hash-gated so day-to-day pushes stay fast);
#   2. `pre-commit run --all-files` (mirrors the pre-commit workflow);
#   3. `python -m pytest` inside that clean venv (mirrors Tests).
#
# Runs on demand (`scripts/check_gate_stamp.sh full`, pre-commit's manual
# stage) and in CI. It left the pre-push path on 2026-09-20: 10+ minutes
# per push under the resource cap, for work finish_auto.sh had just done.
#
# Usage: ci_mirror.sh [venv|precommit|pytest|all] [pytest args...]
#   Each step is its own manual hook (ci-venv, ci-precommit-*, ci-pytest) so no
#   single call outlives the 60 s action cap; `all` (the default) is the old
#   one-shot behaviour. pytest runs under xdist (-n auto --dist worksteal):
#   serial it was ~85 s, and pytest-cov merges the workers' coverage.
# ============================================================================

set -euo pipefail

# Requirements file may be overridden (e.g. testsAndMisc uses meta/…).
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-requirements.txt}"
readonly REQUIREMENTS_FILE

ROOT="$(git rev-parse --show-toplevel)"
readonly ROOT
cd "$ROOT"

readonly VENV_DIR="$ROOT/.ci-mirror-venv"
readonly HASH_FILE="$VENV_DIR/.requirements.sha256"
readonly REQ_PATH="$ROOT/$REQUIREMENTS_FILE"

log() { printf 'ci-mirror: %s\n' "$1" >&2; }

fail() {
    log "FAILED — $1"
    log "CI would be red. Fix the above before pushing."
    exit 1
}

require_file() {
    if [[ ! -f "$REQ_PATH" ]]; then
        fail "requirements file not found: $REQ_PATH"
    fi
}

# Rebuild the venv only when requirements.txt changed since the last build.
ensure_venv() {
    local current stored
    current="$(sha256sum "$REQ_PATH" | cut -d' ' -f1)"
    stored=""
    if [[ -f "$HASH_FILE" ]]; then
        stored="$(cat "$HASH_FILE")"
    fi

    if [[ -x "$VENV_DIR/bin/python" && "$current" == "$stored" ]]; then
        log "venv up to date (requirements.txt unchanged)"
        return
    fi

    log "requirements.txt changed — rebuilding clean venv (mirrors CI install)"
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip \
        || fail "pip self-upgrade in the clean venv"
    "$VENV_DIR/bin/python" -m pip install --quiet -r "$REQ_PATH" \
        || fail "pip install -r $REQUIREMENTS_FILE (a dep may be undeclared)"
    printf '%s' "$current" > "$HASH_FILE"
    log "clean venv ready"
}

# Hooks that get their own group because they dominate the run time. `rest`
# skips them by id (SKIP matches the id, so `pylint` covers both pylint hooks).
readonly HEAVY_IDS="pylint,flutter-analyze,web-lint,web-typecheck"

# One slice of `pre-commit run --all-files`, small enough for the 60 s action
# cap. The groups partition the default-stage hooks: pylint-source and
# pylint-tests (the aliases of the two `pylint` hooks), flutter-web, and rest
# (everything else). With no group, all of it runs in one go, as CI does.
run_precommit_group() {
    local group="${1:-all}"
    log "pre-commit run --all-files [$group] (mirrors the pre-commit workflow)"
    case "$group" in
        all) pre-commit run --all-files ;;
        pylint-source | pylint-tests) pre-commit run "$group" --all-files ;;
        flutter-web)
            pre-commit run flutter-analyze --all-files \
                && pre-commit run web-lint --all-files \
                && pre-commit run web-typecheck --all-files
            ;;
        rest) SKIP="$HEAVY_IDS" pre-commit run --all-files ;;
        *) fail "unknown pre-commit group '$group'" ;;
    esac || fail "pre-commit --all-files [$group]"
}

run_pytest_clean_venv() {
    log "pytest in the clean venv (mirrors the Tests workflow)"
    "$VENV_DIR/bin/python" -m pytest -n auto --dist worksteal "$@" \
        || fail "pytest (clean requirements.txt venv)"
}

main() {
    local mode="all"
    case "${1:-}" in
        venv | precommit | pytest | all) mode="$1"; shift ;;
        *) ;;
    esac

    case "$mode" in
        precommit) run_precommit_group "${1:-all}"; return ;;
        *) ;;
    esac
    require_file
    ensure_venv
    case "$mode" in
        venv) ;;
        pytest) run_pytest_clean_venv "$@" ;;
        *)
            run_precommit_group all
            run_pytest_clean_venv "$@"
            log "all CI gates passed locally — safe to push"
            ;;
    esac
}

main "$@"
