#!/bin/bash

# ============================================================================
# Pair the phone's workout_app with this PC's workout poke listener.
#
# Creates ~/.config/workout_poke/key if missing (workout_poke_keygen.sh), then
# hands it and the PC's LAN address to the app over adb via its
# PairPcReceiver broadcast, which stores both in the Android keystore. Success
# is decided by the broadcast's own reply -- `adb shell` exits 0 even when
# the receiver is missing -- so it needs both `result=-1` and `data="paired"`.
#
# The key is on adb's command line for the broadcast's lifetime (that is the
# receiver's interface) but is never printed.
#
# Usage: pair_phone.sh [--sandbox] [--host IP] [-s SERIAL]
#   --sandbox   pair the sandbox flavor (com.kuhy.workout_app.sandbox)
#   --host IP   the PC address the phone should poke (default 192.168.1.43)
#   -s SERIAL   passed to adb when several devices are attached
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly SCRIPT_NAME="${0##*/}"
readonly KEY_FILE="${HOME}/.config/workout_poke/key"
readonly ACTION="com.kuhy.workout_app.PAIR_PC"
readonly RECEIVER="com.kuhy.workout_app.PairPcReceiver"

PACKAGE="com.kuhy.workout_app"
HOST="192.168.1.43"
ADB_ARGS=()

usage() {
	echo "Usage: $SCRIPT_NAME [--sandbox] [--host IP] [-s SERIAL]"
	exit 0
}

require_adb() {
	if ! command -v adb >/dev/null 2>&1; then
		echo "Installing missing dependency: android-tools (adb)"
		sudo pacman -S --needed --noconfirm android-tools
	fi
}

# The broadcast's reply minus the key, should anything ever echo it back.
redact() {
	local text="$1" key="$2"
	printf '%s\n' "${text//"$key"/<key>}"
}

main() {
	require_adb
	bash "$SCRIPT_DIR/workout_poke_keygen.sh"
	local key output
	key="$(<"$KEY_FILE")"
	echo "Pairing ${PACKAGE} with host ${HOST} ..."
	if ! output="$(adb "${ADB_ARGS[@]}" shell am broadcast \
		-a "$ACTION" \
		-n "${PACKAGE}/${RECEIVER}" \
		--es key "$key" \
		--es host "$HOST" 2>&1)"; then
		echo "Error: adb failed (is the phone connected and authorized?):" >&2
		redact "$output" "$key" >&2
		exit 1
	fi
	if [[ $output == *"result=-1"* && $output == *'data="paired"'* ]]; then
		echo "paired"
		return 0
	fi
	echo "Error: ${PACKAGE} did not confirm the pairing. A missing" \
		"'result=-1' usually means the app (or this flavor) is not installed" \
		"or predates PairPcReceiver. adb said:" >&2
	redact "$output" "$key" >&2
	exit 1
}

while [[ $# -gt 0 ]]; do
	case $1 in
	--sandbox)
		PACKAGE="com.kuhy.workout_app.sandbox"
		shift
		;;
	--host)
		HOST="${2:?--host needs an address}"
		shift 2
		;;
	-s)
		ADB_ARGS=(-s "${2:?-s needs a device serial}")
		shift 2
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

main
