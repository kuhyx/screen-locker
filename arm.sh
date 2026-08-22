#!/bin/bash

# ============================================================================
# Arm the workout screen locker — install units, enable timers, verify.
#
# One command, because re-arming used to be a four-command sequence that was
# easy to half-do. On 2026-08-04 a systemd ordering cycle silently disabled
# early-bird-workout-check.timer and enforcement stopped for thirteen days with
# nothing on the machine saying so; `systemctl enable` alone would NOT have
# caught that, because enable "succeeds" while systemd deletes the timer job.
# So this script always finishes by asking systemd what it actually scheduled,
# and fails loudly when the answer is "nothing".
#
# Usage:
#   ./arm.sh                 # install, enable, verify
#   ./arm.sh --skip-today    # ...but do not lock today (adds a scheduled skip)
#   ./arm.sh --status        # verify only; change nothing
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly USER_UNIT_DIR="$HOME/.config/systemd/user"

# shellcheck source=scripts/disarm_guard.sh
source "$SCRIPT_DIR/scripts/disarm_guard.sh"

# Units that must be on disk for enforcement to be schedulable.
readonly UNITS=(
	"workout-locker.service"
	"workout-locker.timer"
	"early-bird-workout-check.timer"
	"workout-sync.service"
	"workout-sync.timer"
)

# Only the timers get enabled; the service is triggered by them and by login.
readonly TIMERS=(
	"early-bird-workout-check.timer"
	"workout-locker.timer"
	"workout-sync.timer"
)

SKIP_TODAY=0
STATUS_ONLY=0
REARM=0

usage() {
	echo "Usage: $(basename "$0") [--skip-today] [--status] [--rearm]"
	echo "  --skip-today  Arm the locker but exempt today (no lock until tomorrow)"
	echo "  --status      Report whether enforcement is armed; change nothing"
	echo "  --rearm       Clear the disarm marker + unmask units, then arm"
	exit 0
}

verify_armed() {
	python3 "$SCRIPT_DIR/scripts/check_enforcement_armed.py"
}

add_skip_for_today() {
	# Delegated to Python rather than hand-editing JSON in bash: the file is
	# the same one the lock chain reads, and a malformed write would be read as
	# "not a skip" and lock anyway.
	python3 "$SCRIPT_DIR/scripts/add_scheduled_skip.py" --date today
}

main() {
	if ((STATUS_ONLY)); then
		# --status changes nothing, so it stays usable while disarmed - but it
		# must say so loudly, or "armed: no" reads like a bug instead of intent.
		if report_disarmed; then
			return
		fi
		verify_armed
		return
	fi

	if ((REARM)); then
		clear_disarm_marker
	else
		refuse_if_disarmed
	fi

	echo "Installing units into $USER_UNIT_DIR"
	mkdir -p "$USER_UNIT_DIR"
	for unit in "${UNITS[@]}"; do
		cp "$SCRIPT_DIR/$unit" "$USER_UNIT_DIR/$unit"
	done

	systemctl --user daemon-reload

	if ((SKIP_TODAY)); then
		# Register the exemption BEFORE the timers can fire, so arming can
		# never race the first re-check and lock the machine anyway.
		add_skip_for_today
	fi

	echo "Enabling timers"
	systemctl --user enable --now "${TIMERS[@]}"

	# The whole point: `enable` returning 0 is not proof of anything.
	echo ""
	verify_armed
	echo ""
	echo "✓ Screen locker armed."
	if ((SKIP_TODAY)); then
		echo "  Today is exempt — enforcement begins tomorrow."
	fi
}

while [[ $# -gt 0 ]]; do
	case $1 in
	--skip-today)
		SKIP_TODAY=1
		shift
		;;
	--status)
		STATUS_ONLY=1
		shift
		;;
	--rearm)
		REARM=1
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
