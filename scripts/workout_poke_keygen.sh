#!/bin/bash

# ============================================================================
# Create the phone -> PC workout poke key if it does not exist yet.
#
# The key is 32 random bytes as 64 hex characters in
# ~/.config/workout_poke/key (mode 600, dir 700). workout-poke.service verifies
# each poke's HMAC with it and refuses to start without it; pair_phone.sh
# copies it to the phone. An existing key is NEVER overwritten: a new key
# would silently unpair the phone. Prints the path, never the key.
#
# Usage: workout_poke_keygen.sh [--key-file PATH]
# ============================================================================

set -euo pipefail

KEY_FILE="${HOME}/.config/workout_poke/key"
readonly SCRIPT_NAME="${0##*/}"
readonly KEY_HEX_LENGTH=64

usage() {
	echo "Usage: $SCRIPT_NAME [--key-file PATH]"
	exit 0
}

# An existing key must still be well-formed and private, or the daemon will
# refuse it; say so here rather than let the unit fail later.
check_existing_key() {
	local key mode
	mode="$(stat -c '%a' "$KEY_FILE")"
	if [[ $mode != "600" ]]; then
		echo "Error: $KEY_FILE has mode $mode; run: chmod 600 $KEY_FILE" >&2
		exit 1
	fi
	key="$(<"$KEY_FILE")"
	if [[ ! $key =~ ^[0-9a-f]{$KEY_HEX_LENGTH}$ ]]; then
		echo "Error: $KEY_FILE is not $KEY_HEX_LENGTH lowercase hex characters;" \
			"move it aside and re-run (the phone must then be re-paired)" >&2
		exit 1
	fi
	echo "Key already present: $KEY_FILE (left unchanged)"
}

create_key() {
	local dir key
	dir="$(dirname "$KEY_FILE")"
	mkdir -p "$dir"
	chmod 700 "$dir"
	key="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
	if [[ ! $key =~ ^[0-9a-f]{$KEY_HEX_LENGTH}$ ]]; then
		echo "Error: could not read 32 random bytes from /dev/urandom" >&2
		exit 1
	fi
	# umask + noclobber: the file is born 600 and a racing creator loses.
	(
		umask 077
		set -o noclobber
		printf '%s\n' "$key" >"$KEY_FILE"
	)
	echo "Created key: $KEY_FILE (mode 600)"
}

main() {
	if [[ -e $KEY_FILE ]]; then
		check_existing_key
	else
		create_key
	fi
}

while [[ $# -gt 0 ]]; do
	case $1 in
	--key-file)
		KEY_FILE="$2"
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
