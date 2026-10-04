#!/bin/bash
# Helper script to adjust the shutdown schedule, allowed via sudoers.
#
# Usage: sudo adjust_shutdown_schedule.sh [--restore] <mon_wed> <thu_sun> <morning_end>
#
# Each time is HH:MM (00:00-24:00) or a legacy bare whole hour (0-24). The config
# stores minutes after midnight in *_MINUTES plus a strict-rounded *_HOUR copy
# for readers that predate minutes: evening times round DOWN, the morning end
# UP, so an old reader can only ever shut down earlier than intended.
#
# Without --restore only STRICTER schedules are accepted. "Stricter" is not the
# same direction for all three values, which is the subtlety this script got
# wrong for months:
#
#   MON_WED / THU_SUN  -> smaller is stricter (shut down earlier)
#   MORNING_END        -> LARGER is stricter
#
# day-specific-shutdown-check.sh shuts down while the clock is *below*
# morning_end_minutes, so raising the morning end lengthens the morning
# shutdown window. Comparing it with `-gt`, as the two evening hours do, would
# ratchet it backwards and quietly allow the window to be shortened.
#
# With --restore the schedule may be loosened -- that is how the workout reward
# pushes shutdown later -- but never past RESTORE_CEILING, and every restore is
# recorded. Without the ceiling, `--restore 24:00 24:00 00:00` is an off switch
# for the whole ratchet.
#
# Add to /etc/sudoers.d/workout-locker:
#   <username> ALL=(root) NOPASSWD: /home/kuhy/src/screen-locker/screen_locker/adjust_shutdown_schedule.sh

set -euo pipefail

# Overridable so the test harness can point at a fixture tree; production never
# sets these, and the harness sets them explicitly rather than trust a default.
CONFIG_FILE="${SHUTDOWN_CONFIG_FILE:-/etc/shutdown-schedule.conf}"
GUARD_NAME="${SHUTDOWN_GUARD_NAME:-shutdown-schedule}"
readonly CONFIG_FILE GUARD_NAME

# 24:00 (1440) is a real value: _shutdown.py's bonus uses it for midnight, which
# day-specific-shutdown-check.sh catches via the morning-window condition.
readonly MAX_MINUTES=1440
readonly MINUTES_PER_HOUR=60

# The latest the machine may ever shut down, whatever has been earned. --restore
# exists so the workout reward can loosen the schedule, and without a ceiling it
# is simply an off switch for the ratchet. Bonuses above this are clamped, not
# refused, so the reward path keeps working.
readonly RESTORE_CEILING=1380 # 23:00
readonly RESTORE_LOG="${SHUTDOWN_RESTORE_LOG:-/var/log/shutdown-restore.log}"

usage() {
	echo "Usage: $0 [--restore] <mon_wed> <thu_sun> <morning_end>" >&2
	echo "  each time HH:MM (00:00-24:00) or a whole hour (0-24)" >&2
	exit 1
}

# Print a time argument as minutes after midnight. Accepts HH:MM or a bare
# whole hour (the pre-minutes form, still sent by older callers).
to_minutes() {
	local value="$1" minutes
	if [[ "$value" =~ ^([0-9]{1,2}):([0-5][0-9])$ ]]; then
		minutes=$((10#${BASH_REMATCH[1]} * MINUTES_PER_HOUR + 10#${BASH_REMATCH[2]}))
	elif [[ "$value" =~ ^[0-9]{1,2}$ ]]; then
		minutes=$((10#$value * MINUTES_PER_HOUR))
	else
		minutes=-1
	fi
	if [[ $minutes -lt 0 ]] || [[ $minutes -gt $MAX_MINUTES ]]; then
		echo "Error: '${value}' is not a time between 00:00 and 24:00" \
			"(HH:MM, or a whole hour 0-24; 24:00 means midnight)" >&2
		return 1
	fi
	printf '%d' "$minutes"
}

# HH:MM for a count of minutes after midnight.
hhmm() {
	printf '%02d:%02d' "$(($1 / MINUTES_PER_HOUR))" "$(($1 % MINUTES_PER_HOUR))"
}

# A config value in minutes: the *_MINUTES key when present, else the legacy
# *_HOUR key times 60, else the given default.
config_minutes() {
	local minutes="$1" hour="$2" default="$3"
	if [[ "$minutes" =~ ^[0-9]+$ ]]; then
		printf '%d' "$((10#$minutes))"
	elif [[ "$hour" =~ ^[0-9]+$ ]]; then
		printf '%d' "$((10#$hour * MINUTES_PER_HOUR))"
	else
		printf '%d' "$default"
	fi
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
	unset MON_WED_HOUR THU_SUN_HOUR MORNING_END_HOUR \
		MON_WED_MINUTES THU_SUN_MINUTES MORNING_END_MINUTES
	# shellcheck source=/dev/null
	source "$CONFIG_FILE" 2>/dev/null || true
	# Defaults are the LOOSEST value in each direction, so an unreadable config
	# can never reject a legitimate first write.
	old_mon_wed="$(config_minutes "${MON_WED_MINUTES:-}" "${MON_WED_HOUR:-}" "$MAX_MINUTES")"
	old_thu_sun="$(config_minutes "${THU_SUN_MINUTES:-}" "${THU_SUN_HOUR:-}" "$MAX_MINUTES")"
	old_morning_end="$(config_minutes "${MORNING_END_MINUTES:-}" "${MORNING_END_HOUR:-}" 0)"

	if [[ "$new_mon_wed" -gt "$old_mon_wed" ]] ||
		[[ "$new_thu_sun" -gt "$old_thu_sun" ]]; then
		echo "Error: Can only make schedule stricter (earlier shutdown times)" >&2
		echo "Use --restore flag to restore original times" >&2
		return 1
	fi

	# Note the inverted comparison: a SMALLER morning end is looser.
	if [[ "$new_morning_end" -lt "$old_morning_end" ]]; then
		echo "Error: Can only make schedule stricter (a later morning end)" >&2
		echo "  $(hhmm "$old_morning_end") -> $(hhmm "$new_morning_end") shortens the" \
			"morning shutdown window" >&2
		echo "Use --restore flag to restore original times" >&2
		return 1
	fi
}

# Clamp a restore to the ceiling and record that it happened.
#
# Deliberately NOT written to /etc/shutdown-schedule-overrides.conf: that file
# is parsed by day-specific-shutdown-check.sh as start|end|created|reason, and a
# line matching the current time makes it exit 0 and skip the shutdown outright.
# An "audit trail" written there would suppress the very curfew it documents.
clamp_restore() {
	local minutes="$1" label="$2"
	if [[ "$minutes" -gt $RESTORE_CEILING ]]; then
		echo "Note: ${label} $(hhmm "$minutes") clamped to the" \
			"$(hhmm "$RESTORE_CEILING") ceiling" >&2
		printf '%s' "$RESTORE_CEILING"
		return 0
	fi
	printf '%s' "$minutes"
}

# A restore that is not recorded is a loosening nobody can audit, so a failure
# to write the log says so on stderr rather than being swallowed. It is not
# fatal: refusing the reward because a log file is unwritable would be worse
# than the missing line.
log_restore() {
	local line
	line="$(date -Is) | RESTORE | mon_wed=$(hhmm "$1") thu_sun=$(hhmm "$2") morning_end=$(hhmm "$3") | by=${SUDO_USER:-${USER:-unknown}}"
	if ! printf '%s\n' "$line" >>"$RESTORE_LOG" 2>/dev/null; then
		echo "Warning: could not record this restore in ${RESTORE_LOG};" \
			"the schedule was still loosened" >&2
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

# The config body. *_MINUTES is authoritative; *_HOUR is the strict-rounded
# copy for pre-minutes readers (evening down, morning end up).
render_schedule() {
	local mon_wed="$1" thu_sun="$2" morning_end="$3"
	printf '%s\n' \
		"# Shutdown schedule configuration" \
		"# Modified by screen_locker sick day feature at $(date)" \
		"# *_MINUTES = minutes after midnight (authoritative); *_HOUR = the same" \
		"# time rounded the strict way, for readers that predate minutes." \
		"MON_WED_MINUTES=${mon_wed}" \
		"THU_SUN_MINUTES=${thu_sun}" \
		"MORNING_END_MINUTES=${morning_end}" \
		"MON_WED_HOUR=$((mon_wed / MINUTES_PER_HOUR))" \
		"THU_SUN_HOUR=$((thu_sun / MINUTES_PER_HOUR))" \
		"MORNING_END_HOUR=$(((morning_end + MINUTES_PER_HOUR - 1) / MINUTES_PER_HOUR))"
}

main() {
	local restore_mode=false
	if [[ "${1:-}" == "--restore" ]]; then
		restore_mode=true
		shift
	fi

	[[ $# -eq 3 ]] || usage
	local mon_wed thu_sun morning_end
	mon_wed="$(to_minutes "$1")" || exit 1
	thu_sun="$(to_minutes "$2")" || exit 1
	morning_end="$(to_minutes "$3")" || exit 1

	if [[ "$restore_mode" == false ]]; then
		check_stricter_only "$mon_wed" "$thu_sun" "$morning_end" || exit 1
	else
		# A restore may loosen, but never past the ceiling, and never silently.
		mon_wed="$(clamp_restore "$mon_wed" "Mon-Wed")"
		thu_sun="$(clamp_restore "$thu_sun" "Thu-Sun")"
		log_restore "$mon_wed" "$thu_sun" "$morning_end"
	fi

	local canonical body
	canonical="$(resolve_canonical)" || exit 1
	body="$(render_schedule "$mon_wed" "$thu_sun" "$morning_end")"$'\n'
	write_schedule "$canonical" "$body"

	echo "Shutdown schedule updated: Mon-Wed=$(hhmm "$mon_wed")," \
		"Thu-Sun=$(hhmm "$thu_sun"), Morning end=$(hhmm "$morning_end")"
}

# Sourced by the test harness; executed in production.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
	main "$@"
fi
