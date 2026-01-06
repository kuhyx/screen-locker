#!/bin/bash
# Helper script to adjust shutdown schedule
# This script should be allowed via sudoers for the workout locker
#
# Usage: sudo adjust_shutdown_schedule.sh [--restore] <mon_wed_hour> <thu_sun_hour> <morning_end_hour>
#
# --restore: Allow restoring to original (possibly later) times
#            Without this flag, only stricter (earlier) times are allowed
#
# Add to /etc/sudoers.d/workout-locker:
#   <username> ALL=(root) NOPASSWD: /home/kuhy/testsAndMisc/python_pkg/screen_locker/adjust_shutdown_schedule.sh

set -euo pipefail

CONFIG_FILE="/etc/shutdown-schedule.conf"
CANONICAL_FILE="/usr/local/share/locked-shutdown-schedule.conf"

# Check for --restore flag
RESTORE_MODE=false
if [[ "${1:-}" == "--restore" ]]; then
    RESTORE_MODE=true
    shift
fi

# Validate arguments
if [[ $# -ne 3 ]]; then
    echo "Usage: $0 [--restore] <mon_wed_hour> <thu_sun_hour> <morning_end_hour>" >&2
    exit 1
fi

MON_WED_HOUR="$1"
THU_SUN_HOUR="$2"
MORNING_END_HOUR="$3"

# Validate hours are integers between 0-23
for hour in "$MON_WED_HOUR" "$THU_SUN_HOUR" "$MORNING_END_HOUR"; do
    if ! [[ "$hour" =~ ^[0-9]+$ ]] || [[ "$hour" -lt 0 ]] || [[ "$hour" -gt 23 ]]; then
        echo "Error: Hours must be integers between 0 and 23" >&2
        exit 1
    fi
done

# Read current values to check if we're making schedule stricter
if [[ -f "$CONFIG_FILE" ]] && [[ "$RESTORE_MODE" == false ]]; then
    # shellcheck source=/dev/null
    source "$CONFIG_FILE" 2>/dev/null || true
    OLD_MON_WED="${MON_WED_HOUR:-24}"
    OLD_THU_SUN="${THU_SUN_HOUR:-24}"

    # Reset variables to new values for comparison
    # shellcheck disable=SC2034
    MON_WED_HOUR_OLD="$OLD_MON_WED"
    # shellcheck disable=SC2034
    THU_SUN_HOUR_OLD="$OLD_THU_SUN"

    # Only allow making schedule stricter (earlier shutdown) unless in restore mode
    if [[ "$1" -gt "${MON_WED_HOUR_OLD:-24}" ]] || [[ "$2" -gt "${THU_SUN_HOUR_OLD:-24}" ]]; then
        echo "Error: Can only make schedule stricter (earlier shutdown times)" >&2
        echo "Use --restore flag to restore original times" >&2
        exit 1
    fi
fi

NEW_CONFIG="# Shutdown schedule configuration
# Modified by screen_locker sick day feature at $(date)
MON_WED_HOUR=$1
THU_SUN_HOUR=$2
MORNING_END_HOUR=$3
"

# Remove immutable attributes
chattr -i "$CONFIG_FILE" 2>/dev/null || true
chattr -i "$CANONICAL_FILE" 2>/dev/null || true

# Write new config
echo "$NEW_CONFIG" > "$CONFIG_FILE"
echo "$NEW_CONFIG" > "$CANONICAL_FILE"

# Set permissions
chmod 644 "$CONFIG_FILE"
chmod 644 "$CANONICAL_FILE"

# Re-apply immutable attributes
chattr +i "$CONFIG_FILE" || echo "Warning: Could not set immutable on $CONFIG_FILE" >&2
chattr +i "$CANONICAL_FILE" || echo "Warning: Could not set immutable on $CANONICAL_FILE" >&2

echo "Shutdown schedule updated: Mon-Wed=${1}:00, Thu-Sun=${2}:00, Morning end=${3}:00"
