#!/usr/bin/env bash
# Tests for the shutdown-schedule ratchet: time parsing and the stricter-only
# check. The write path (dual keys, rounding, --restore) is in
# test_adjust_shutdown_schedule_write.sh; both share _adjust_harness.sh.
#
# This ratchet had no test at all, which is how the morning end went unchecked
# for months while the two evening times were guarded. The direction cases
# below are the point of the file: "stricter" means SMALLER for the evening
# times and LARGER for the morning end. Times are minutes after midnight.
set -uo pipefail

# shellcheck source=_adjust_harness.sh
source "$(dirname "${BASH_SOURCE[0]}")/_adjust_harness.sh"

echo "to_minutes"
_t_eq "1260" "$(to_minutes 21:00)" "HH:MM becomes minutes"
_t_eq "1110" "$(to_minutes 18:30)" "keeps the minutes of 18:30"
_t_eq "1260" "$(to_minutes 21)" "a legacy bare hour is hours x 60"
_t_eq "1440" "$(to_minutes 24:00)" "24:00 means midnight"
_t_eq "300" "$(to_minutes 5)" "a one-digit hour works"
_t_eq "300" "$(to_minutes 05:00)" "a zero-padded hour is not read as octal"
_t_eq "540" "$(to_minutes 09:00)" "09:00 is not read as octal"
_t_blocks "rejects a non-time" to_minutes abc
_t_blocks "rejects 24:30 (past midnight)" to_minutes 24:30
_t_blocks "rejects 25 (the old out-of-range hour)" to_minutes 25
_t_blocks "rejects minutes of 60" to_minutes 12:60
_t_blocks "rejects a negative (the minus makes it non-numeric)" to_minutes -1
_t_eq "21:05" "$(hhmm 1265)" "hhmm renders minutes zero-padded"

echo "check_stricter_only: evening times (smaller is stricter)"
write_config 1380 1380 300
_t_allows "allows an earlier Mon-Wed" check_stricter_only 1260 1380 300
_t_allows "allows an unchanged schedule" check_stricter_only 1380 1380 300
_t_blocks "blocks a later Mon-Wed" check_stricter_only 1440 1380 300
_t_blocks "blocks a later Thu-Sun" check_stricter_only 1380 1440 300

echo "check_stricter_only: minute precision"
write_config 1260 1260 300
_t_blocks "blocks 21:01 when 21:00 is live" check_stricter_only 1261 1260 300
_t_allows "allows 20:59 when 21:00 is live" check_stricter_only 1259 1260 300
_t_allows "allows an 18:30 Thu-Sun when 21:00 is live" \
	check_stricter_only 1260 1110 300

echo "check_stricter_only: morning end (LARGER is stricter -- inverted)"
write_config 1380 1380 300
_t_allows "allows a later morning end, which lengthens the window" \
	check_stricter_only 1380 1380 420
_t_blocks "blocks an earlier morning end, which shortens the window" \
	check_stricter_only 1380 1380 180
_t_blocks "blocks a morning end only 1 minute earlier" \
	check_stricter_only 1380 1380 299
out="$(check_stricter_only 1380 1380 180 2>&1 || true)"
_t_has "$out" "shortens the" "explains WHY the morning end was rejected"

echo "check_stricter_only: the source-clobber trap"
# `source` overwrites the config variables with the OLD values. If the
# comparison read those globals instead of its arguments it would compare a
# value with itself and pass everything.
write_config 1260 1260 300
_t_blocks "still blocks a loosening after source has clobbered the globals" \
	check_stricter_only 1380 1380 300

echo "check_stricter_only: a legacy hour-only config reads as the old values"
write_legacy_config 21 21 5
_t_blocks "blocks 21:01 against a legacy 21" check_stricter_only 1261 1260 300
_t_allows "allows 21:00 against a legacy 21" check_stricter_only 1260 1260 300
_t_blocks "blocks a morning end below a legacy 5" \
	check_stricter_only 1260 1260 299
write_config 1110 1110 300
{ printf 'MON_WED_HOUR=23\n'; } >>"$SHUTDOWN_CONFIG_FILE"
_t_blocks "the *_MINUTES key wins over a stale *_HOUR key" \
	check_stricter_only 1200 1110 300

echo "check_stricter_only: missing or unreadable config"
rm -f "$SHUTDOWN_CONFIG_FILE"
_t_allows "allows any write when no config exists yet" \
	check_stricter_only 1380 1380 0
printf 'garbage not a config\n' >"$SHUTDOWN_CONFIG_FILE"
_t_allows "falls back to the loosest defaults rather than rejecting" \
	check_stricter_only 1380 1380 0

_t_summary
