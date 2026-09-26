#!/usr/bin/env bash
# Enforces 100% line coverage for the Flutter workout app.
#
# Run from the repo root. Fails if:
#   1. Any lib/**/*.dart file is missing from coverage/lcov.info (unreachable
#      file — the 100% would be fake without this check).
#   2. Line coverage across all lib/ files is below 100%.
#
# Usage:
#   scripts/check_flutter_coverage.sh               whole suite, then both checks
#   scripts/check_flutter_coverage.sh --shard I/N   test bucket I of N (0-based)
#                                                   only; leaves its lcov.info,
#                                                   checks nothing
#   scripts/check_flutter_coverage.sh --merged N LCOV...
#                                                   union N shards' lcov files
#                                                   into coverage/lcov.info,
#                                                   then both checks
#
# Why shards: the suite took ~150 s on one 4-core runner, almost all of it
# compiling 77 test files. `flutter test --total-shards` cannot help -- it
# splits the test CASES inside every file, so each shard still compiles all
# 77 -- hence buckets of whole files, one per CI runner, and a fan-in job that
# runs the same two checks on their union.
set -euo pipefail

APP_DIR="stronglift_replacement/workout_app"
LCOV_INFO="$APP_DIR/coverage/lcov.info"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

# Runs `flutter test --coverage` in the app, on the given test files (none =
# the whole suite).
run_flutter_tests() {
  echo "Running flutter test --coverage ..."
  # env -u GIT_DIR: git exports it to hooks, and the flutter tool shells out to
  # git to identify its own SDK. With it set, flutter reads THIS repository as
  # the SDK -- reporting our HEAD as the framework revision -- and pub then
  # resolves every version constraint against "0.0.0-unknown" and fails.
  # FLUTTER_TEST_CONCURRENCY: one test isolate per core is the default and
  # peaks well over 4 GiB on this suite, which the 4 GiB resource cap
  # (capped.sh) OOM-kills. Set it to 1-2 under the cap; unset keeps the default.
  local concurrency=()
  if [[ -n "${FLUTTER_TEST_CONCURRENCY:-}" ]]; then
    concurrency=(--concurrency "$FLUTTER_TEST_CONCURRENCY")
  fi
  (cd "$APP_DIR" && env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
    flutter test --coverage "${concurrency[@]}" "$@")
}

# Prints bucket INDEX of TOTAL: every TOTAL-th test file, in a fixed sort
# order, so the N buckets partition the suite exactly.
shard_files() {
  local index=$1 total=$2 i=0 file
  while IFS= read -r file; do
    if (( i % total == index )); then
      printf '%s\n' "$file"
    fi
    i=$(( i + 1 ))
  done < <(cd "$APP_DIR" && find test -name '*_test.dart' | LC_ALL=C sort)
}

# Writes to OUT the union of the given lcov files: per source file, every
# line any shard instrumented, hit if any shard hit it -- which is what one
# unsharded run reports, since flutter merges its test isolates the same way.
# LF/LH are recomputed from that union rather than summed, because a lib file
# loaded by two shards would otherwise count its lines twice.
merge_lcov() {
  local out=$1 file line sf="" rest ln hits key lf lh
  shift
  local -A hit=() lines_of=() seen=()
  local -a order=()
  for file in "$@"; do
    while IFS= read -r line; do
      case $line in
        SF:*)
          sf=${line#SF:}
          if [[ -z ${seen[$sf]:-} ]]; then
            seen[$sf]=1
            order+=("$sf")
          fi
          ;;
        DA:*)
          rest=${line#DA:}
          ln=${rest%%,*}
          rest=${rest#*,}
          hits=${rest%%,*}
          key="$sf|$ln"
          if [[ -z ${hit[$key]:-} ]]; then
            hit[$key]=$hits
            lines_of[$sf]+="$ln "
          else
            hit[$key]=$(( hit[$key] + hits ))
          fi
          ;;
      esac
    done < "$file"
  done
  mkdir -p "$(dirname "$out")"
  for sf in "${order[@]}"; do
    echo "SF:$sf"
    lf=0
    lh=0
    for ln in ${lines_of[$sf]:-}; do
      echo "DA:$ln,${hit[$sf|$ln]}"
      lf=$(( lf + 1 ))
      if (( hit[$sf|$ln] > 0 )); then
        lh=$(( lh + 1 ))
      fi
    done
    echo "LF:$lf"
    echo "LH:$lh"
    echo "end_of_record"
  done > "$out"
}

case "${1:-}" in
  "")
    run_flutter_tests
    ;;
  --shard)
    [[ ${2:-} =~ ^([0-9]+)/([1-9][0-9]*)$ ]] || die "--shard wants I/N, got '${2:-}'"
    index=${BASH_REMATCH[1]}
    total=${BASH_REMATCH[2]}
    (( index < total )) || die "shard index $index is not below $total"
    mapfile -t files < <(shard_files "$index" "$total")
    (( ${#files[@]} > 0 )) || die "shard $index/$total has no test files"
    echo "Shard $index/$total: ${#files[@]} test files"
    run_flutter_tests "${files[@]}"
    exit 0
    ;;
  --merged)
    [[ ${2:-} =~ ^[1-9][0-9]*$ ]] || die "--merged wants a shard count first"
    expected=$2
    shift 2
    # A shard whose artifact went missing would quietly shrink the union.
    (( $# == expected )) || die "expected $expected shard lcov files, got $#"
    merge_lcov "$LCOV_INFO" "$@"
    ;;
  *)
    die "unknown argument '$1' (see the usage at the top of $0)"
    ;;
esac

if [[ ! -f "$LCOV_INFO" ]]; then
  echo "ERROR: $LCOV_INFO not found — did flutter test run?" >&2
  exit 1
fi

# ── Guard: every lib/**/*.dart must appear in the coverage report ──────────────
# Flutter only reports files that are transitively imported by a test.
# Unreferenced files silently score 100% by absence — catch that here.
#
# Exception: a file whose only content is a conditional `export` (a
# platform-gate barrel like google_platform.dart, re-exporting google_platform_io.dart
# or google_platform_web.dart per dart.library.js_interop) has zero executable
# statements. Dart's coverage instrumentation never emits an SF: entry for such
# a file regardless of whether it was imported -- there is no "silently 100% by
# absence" for it to hide, since there is nothing to cover. Importing it (even
# transitively) is what makes its *resolved* sibling appear in lcov instead.
barrel_pattern="^(library;)?[[:space:]]*export[[:space:]]+'[^']+'[[:space:]]+if[[:space:]]*\([^)]+\)[[:space:]]+'[^']+';[[:space:]]*\$"

missing=0
while IFS= read -r dart_file; do
  rel="${dart_file#"$APP_DIR"/}"
  # Strip //-comments, ///-doc-comments and blank lines, then collapse
  # whitespace, so a wrapped `export 'x' if (...) 'y';` statement (the
  # platform-gate barrel shape) becomes matchable on one logical line
  # regardless of how it's line-wrapped in source.
  code_only=$(grep -vE '^[[:space:]]*(///|//|$)' "$dart_file" | tr '\n' ' ' | tr -s ' ')
  if [[ $code_only =~ $barrel_pattern ]]; then
    continue
  fi
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
