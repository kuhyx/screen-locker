#!/bin/bash

# ============================================================================
# Finish the 2026-08-24 "workout not found" recovery, end to end.
#
# Everything Claude could not run itself, in the one order that works. The
# ordering is not cosmetic: `sick_day` fires BEFORE `already_logged` in the
# lock chain, so while the sick day stands it short-circuits the decision and
# hides whether the workout credit actually landed. Credit first, revoke
# second, re-arm last.
#
# Safe to re-run: every step is idempotent, and the script stops at the first
# failure rather than pressing on to re-arm a locker that cannot see today's
# workout.
#
# Usage:
#   ./scripts/finish_2026_08_24.sh            # do everything, then re-arm
#   ./scripts/finish_2026_08_24.sh --no-arm   # ...but leave enforcement off
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SCRIPT_DIR
readonly PY="$SCRIPT_DIR/.venv/bin/python"
readonly TARGET_DATE="2026-08-24"

ARM=1

usage() {
	echo "Usage: $(basename "$0") [--no-arm]"
	echo "  --no-arm   Run every step but leave enforcement disarmed"
	exit 0
}

step() {
	echo ""
	echo "=============================================================="
	echo "  $1"
	echo "=============================================================="
}

validate_requirements() {
	if [[ ! -x $PY ]]; then
		echo "Error: no venv interpreter at $PY — run ./run.sh once first" >&2
		exit 1
	fi
}

main() {
	validate_requirements
	cd "$SCRIPT_DIR"

	step "1/7  Test suite (must be green before touching live state)"
	"$PY" -m pytest screen_locker/tests/ -q --no-cov

	step "2/7  Lint + type gate"
	"$PY" -m pre_commit run --all-files

	step "3/7  Sync: recover Firebase, then ingest today's workout"
	# --sync-only never locks, so this is safe to run while disarmed.
	./run.sh --sync-only

	step "4/7  Did $TARGET_DATE actually land in the log?"
	# Gate, don't warn: if the credit is not on disk there is nothing to
	# revoke a sick day against, and re-arming here would lock you out again.
	"$PY" scripts/verify_workout_credited.py --date "$TARGET_DATE"

	step "5/7  Restore shutdown hours + grant the bonus"
	"$PY" scripts/restore_and_bonus.py --date "$TARGET_DATE"

	step "6/7  Revoke the sick days that this workout disproves"
	"$PY" scripts/revoke_sick_day.py --date "$TARGET_DATE" --date 2026-06-12

	if ((ARM)); then
		step "7/7  Re-arm enforcement"
		./arm.sh --rearm
	else
		step "7/7  Skipped re-arm (--no-arm); enforcement stays OFF"
		echo "Re-arm later with: ./arm.sh --rearm"
	fi

	echo ""
	echo "✓ Done."
}

while [[ $# -gt 0 ]]; do
	case $1 in
	--no-arm)
		ARM=0
		shift
		;;
	-h | --help)
		usage
		;;
	*)
		echo "Unknown option: $1" >&2
		exit 1
		;;
	esac
done

main "$@"
