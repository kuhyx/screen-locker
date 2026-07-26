#!/usr/bin/env bash
# Enforces 100% line coverage for the Flutter workout app.
#
# Run from the repo root. Fails if:
#   1. Any lib/**/*.dart file is missing from coverage/lcov.info (unreachable
#      file — the 100% would be fake without this check).
#   2. Line coverage across all lib/ files is below 100%.
#
# Usage: scripts/check_flutter_coverage.sh
set -euo pipefail

APP_DIR="stronglift_replacement/workout_app"
LCOV_INFO="$APP_DIR/coverage/lcov.info"

cd "$APP_DIR"

echo "Running flutter test --coverage ..."
# env -u GIT_DIR: git exports it to hooks, and the flutter tool shells out to
# git to identify its own SDK. With it set, flutter reads THIS repository as
# the SDK -- reporting our HEAD as the framework revision -- and pub then
# resolves every version constraint against "0.0.0-unknown" and fails.
env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE flutter test --coverage

cd - > /dev/null

if [[ ! -f "$LCOV_INFO" ]]; then
  echo "ERROR: $LCOV_INFO not found — did flutter test run?" >&2
  exit 1
fi

# ── Guard: every lib/**/*.dart must appear in the coverage report ──────────────
# Flutter only reports files that are transitively imported by a test.
# Unreferenced files silently score 100% by absence — catch that here.
missing=0
while IFS= read -r dart_file; do
  rel="${dart_file#"$APP_DIR"/}"
  if ! grep -qF "SF:$rel" "$LCOV_INFO" && \
     ! grep -qF "SF:lib/${rel#lib/}" "$LCOV_INFO"; then
    echo "MISSING FROM COVERAGE: $dart_file" >&2
    missing=1
  fi
done < <(find "$APP_DIR/lib" -name "*.dart" ! -path "*/generated/*")

if [[ $missing -eq 1 ]]; then
  echo ""
  echo "ERROR: Some lib/ files are not covered. Import them in a test." >&2
  exit 1
fi

# ── Compute line coverage percentage from lcov.info ───────────────────────────
total_found=0
total_hit=0
while IFS= read -r line; do
  if [[ $line == LF:* ]]; then
    total_found=$(( total_found + ${line#LF:} ))
  elif [[ $line == LH:* ]]; then
    total_hit=$(( total_hit + ${line#LH:} ))
  fi
done < "$LCOV_INFO"

if [[ $total_found -eq 0 ]]; then
  echo "ERROR: No line coverage data found in $LCOV_INFO" >&2
  exit 1
fi

if [[ $total_hit -lt $total_found ]]; then
  missed=$(( total_found - total_hit ))
  echo "ERROR: Line coverage is not 100% — $missed/$total_found lines not covered." >&2
  echo "Run: flutter test --coverage && genhtml coverage/lcov.info -o coverage/html" >&2
  exit 1
fi

echo "Coverage OK: $total_hit/$total_found lines covered (100%)."
