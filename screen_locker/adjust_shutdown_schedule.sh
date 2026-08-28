#!/bin/bash
# Helper script to adjust the shutdown schedule, allowed via sudoers.
#
# Usage: sudo adjust_shutdown_schedule.sh [--restore] <mon_wed> <thu_sun> <morning_end>
#
# Without --restore only STRICTER schedules are accepted. "Stricter" is not the
# same direction for all three values, which is the subtlety this script got
# wrong for months:
#
#   MON_WED_HOUR / THU_SUN_HOUR  -> smaller is stricter (shut down earlier)
#   MORNING_END_HOUR             -> LARGER is stricter
#
# day-specific-shutdown-check.sh shuts down while the clock is *below*
# morning_end_minutes, so raising MORNING_END_HOUR lengthens the morning
# shutdown window. Comparing it with `-gt`, as the two evening hours do, would
# ratchet it backwards and quietly allow the window to be shortened.
#
# Add to /etc/sudoers.d/workout-locker:
#   <username> ALL=(root) NOPASSWD: /home/kuhy/screen-locker/screen_locker/adjust_shutdown_schedule.sh

set -euo pipefail

# Overridable so the test harness can point at a fixture tree. Production never
# sets these; a test that forgets to is writing to the real /etc, which is why
# the harness sets both explicitly rather than relying on a default.
CONFIG_FILE="${SHUTDOWN_CONFIG_FILE:-/etc/shutdown-schedule.conf}"
GUARD_NAME="${SHUTDOWN_GUARD_NAME:-shutdown-schedule}"
readonly CONFIG_FILE GUARD_NAME

readonly MAX_HOUR=23

usage() {
	echo "Usage: $0 [--restore] <mon_wed_hour> <thu_sun_hour> <morning_end_hour>" >&2
	exit 1
}

# Validate that every argument is an hour in [0, 23].
validate_hours() {
	local hour
	for hour in "$@"; do
		if ! [[ "$hour" =~ ^[0-9]+$ ]] || [[ "$hour" -gt $MAX_HOUR ]]; then
			echo "Error: Hours must be integers between 0 and ${MAX_HOUR}" >&2
			return 1
		fi
	done
}

# Reject a schedule that is looser than the one currently on disk.
#
# Reads the OLD values by sourcing the config, which overwrites any same-named
# variable in this shell -- so the new values must be passed in as arguments and
# never read from a global. Getting that wrong compares a value with itself and
# always passes.
check_stricter_only() {
	local new_mon_wed="$1" new_thu_sun="$2" new_morning_end="$3"
	local old_mon_wed old_thu_sun old_morning_end

	[[ -f "$CONFIG_FILE" ]] || return 0

	# Cleared first so a config that is present but unreadable falls back to the
	# defaults below instead of silently inheriting whatever these names last
	# held. In production the script is a fresh process and they are unset
	# anyway; this makes the function honest when called twice in one shell.
	unset MON_WED_HOUR THU_SUN_HOUR MORNING_END_HOUR
	# shellcheck source=/dev/null
	source "$CONFIG_FILE" 2>/dev/null || true
	# Defaults are the LOOSEST value in each direction, so an unreadable config
	# can never reject a legitimate first write.
	old_mon_wed="${MON_WED_HOUR:-$MAX_HOUR}"
	old_thu_sun="${THU_SUN_HOUR:-$MAX_HOUR}"
	old_morning_end="${MORNING_END_HOUR:-0}"

	if [[ "$new_mon_wed" -gt "$old_mon_wed" ]] ||
		[[ "$new_thu_sun" -gt "$old_thu_sun" ]]; then
		echo "Error: Can only make schedule stricter (earlier shutdown times)" >&2
		echo "Use --restore flag to restore original times" >&2
		return 1
	fi

	# Note the inverted comparison: a SMALLER morning end is looser.
	if [[ "$new_morning_end" -lt "$old_morning_end" ]]; then
		echo "Error: Can only make schedule stricter (a later morning end)" >&2
		echo "  ${old_morning_end}:00 -> ${new_morning_end}:00 shortens the" \
			"morning shutdown window" >&2
		echo "Use --restore flag to restore original times" >&2
		return 1
	fi
}

# Resolve the guard-lib canonical copy, failing loudly when the guard is absent.
resolve_canonical() {
	local canonical
	canonical="$(guardctl file-guard canonical-path "$GUARD_NAME" 2>/dev/null || true)"
	if [[ -z "$canonical" ]]; then
		echo "Error: guard-lib instance '$GUARD_NAME' is not installed" \
			"(guardctl file-guard canonical-path returned empty)" >&2
		return 1
	fi
	printf '%s' "$canonical"
}

# Write both copies, canonical first.
#
# Order matters: shutdown-schedule-guard.path triggers on CONFIG_FILE and
# restores it from the canonical copy, so writing the watched file first races
# the guard and loses.
write_schedule() {
	local canonical="$1" body="$2"

	chattr -i "$CONFIG_FILE" 2>/dev/null || true
	chattr -i "$canonical" 2>/dev/null || true

	printf '%s' "$body" >"$canonical"
	chmod 644 "$canonical"
	chattr +i "$canonical" || echo "Warning: Could not set immutable on $canonical" >&2

	printf '%s' "$body" >"$CONFIG_FILE"
	chmod 644 "$CONFIG_FILE"
	chattr +i "$CONFIG_FILE" || echo "Warning: Could not set immutable on $CONFIG_FILE" >&2
}

main() {
	local restore_mode=false
	if [[ "${1:-}" == "--restore" ]]; then
		restore_mode=true
		shift
	fi

	[[ $# -eq 3 ]] || usage
	local mon_wed="$1" thu_sun="$2" morning_end="$3"

	validate_hours "$mon_wed" "$thu_sun" "$morning_end" || exit 1

	if [[ "$restore_mode" == false ]]; then
		check_stricter_only "$mon_wed" "$thu_sun" "$morning_end" || exit 1
	fi

	local canonical body
	canonical="$(resolve_canonical)" || exit 1
	body="# Shutdown schedule configuration
# Modified by screen_locker sick day feature at $(date)
MON_WED_HOUR=${mon_wed}
THU_SUN_HOUR=${thu_sun}
MORNING_END_HOUR=${morning_end}
"
	write_schedule "$canonical" "$body"

	echo "Shutdown schedule updated: Mon-Wed=${mon_wed}:00," \
		"Thu-Sun=${thu_sun}:00, Morning end=${morning_end}:00"
}

# Sourced by the test harness; executed in production.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
	main "$@"
fi
