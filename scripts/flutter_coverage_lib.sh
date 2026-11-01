#!/usr/bin/env bash
# Helpers for check_flutter_coverage.sh (sourced, never run): test bucketing,
# lcov union, and the clean-tree guards of the local-gate shard hooks. Split out
# to keep both files under the 250-line cap. Expects APP_DIR, GATE_SHARDS and
# die() from the caller.

# Prints bucket INDEX of TOTAL: every TOTAL-th test file, in a fixed sort
# order, so the N buckets partition the suite exactly.
shard_files() {
  local index=$1 total=$2 i=0 file
  while IFS= read -r file; do
    if (( i % total == index )); then
      printf '%s\n' "$file"
    fi
    i=$(( i + 1 ))
  done < <(cd "$APP_DIR" && git ls-files -- 'test/*_test.dart' | LC_ALL=C sort)
}

# Gate helpers -----------------------------------------------------------------

gate_dir() {
  printf '%s/coverage-shards\n' "$(git rev-parse --git-dir)"
}

# Refuses unless the working tree is exactly HEAD: the stamp records HEAD's
# tree, so the tests must have seen nothing else. Untracked files are ignored
# on purpose (as gate_stamp.sh does); shard_files only lists tracked tests.
require_clean_tree() {
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] \
    || die "working tree differs from HEAD -- commit first, then run the gate."
}

# Ensures the hook list in .pre-commit-config.yaml has GATE_SHARDS shards, so
# raising/lowering the constant alone cannot silently drop a bucket.
require_hooks_match() {
  local n
  n=$(grep -c '^      - id: flutter-test-coverage-shard-' .pre-commit-config.yaml || true)
  (( n == GATE_SHARDS )) \
    || die ".pre-commit-config.yaml declares $n flutter-test-coverage-shard-* hooks, GATE_SHARDS is $GATE_SHARDS"
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
