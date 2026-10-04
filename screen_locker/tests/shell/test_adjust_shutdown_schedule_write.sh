#!/usr/bin/env bash
# Tests for what adjust_shutdown_schedule.sh WRITES: HH:MM and legacy bare-hour
# arguments, the dual-key config (authoritative *_MINUTES plus strict-rounded
# *_HOUR: evening floor, morning ceil), and the --restore ceiling. The parsing
# and stricter-only checks are in test_adjust_shutdown_schedule.sh.
set -uo pipefail

# shellcheck source=_adjust_harness.sh
source "$(dirname "${BASH_SOURCE[0]}")/_adjust_harness.sh"

echo "end to end: HH:MM arguments, dual-key output"
write_config 1380 1380 300
_t_allows "a stricter HH:MM write succeeds" run_main 21:00 21:00 05:00
body="$(cat "$SHUTDOWN_CONFIG_FILE")"
_t_has "$body" "MON_WED_MINUTES=1260" "authoritative minutes key written"
_t_has "$body" "MON_WED_HOUR=21" "legacy hour key written alongside it"
_t_has "$(cat "$FAKE_CANONICAL")" "MON_WED_MINUTES=1260" "canonical copy written too"
write_config 1380 1380 300
_t_blocks "a looser write is refused" run_main 24:00 24:00 05:00
_t_has "$(cat "$SHUTDOWN_CONFIG_FILE")" "MON_WED_MINUTES=1380" \
	"a refused write leaves the config untouched"

echo "end to end: strict rounding of the legacy hour keys"
write_config 1380 1380 300
run_main 18:30 18:59 05:30 >/dev/null 2>&1
body="$(cat "$SHUTDOWN_CONFIG_FILE")"
_t_has "$body" "MON_WED_MINUTES=1110" "18:30 stored exactly"
_t_has "$body" "MON_WED_HOUR=18" "an evening time rounds DOWN (18:30 -> 18)"
_t_has "$body" "THU_SUN_HOUR=18" "18:59 rounds DOWN to 18"
_t_has "$body" "MORNING_END_MINUTES=330" "05:30 stored exactly"
_t_has "$body" "MORNING_END_HOUR=6" "the morning end rounds UP (05:30 -> 6)"
write_config 1380 1380 300
run_main 21:00 21:00 05:00 >/dev/null 2>&1
_t_has "$(cat "$SHUTDOWN_CONFIG_FILE")" "MORNING_END_HOUR=5" \
	"a whole-hour morning end is unchanged by the ceiling"

echo "end to end: legacy bare-hour arguments"
write_config 1380 1380 300
run_main 21 20 5 >/dev/null 2>&1
body="$(cat "$SHUTDOWN_CONFIG_FILE")"
_t_has "$body" "MON_WED_MINUTES=1260" "bare 21 is stored as 1260 minutes"
_t_has "$body" "THU_SUN_MINUTES=1200" "bare 20 is stored as 1200 minutes"
_t_has "$body" "MORNING_END_MINUTES=300" "bare 5 is stored as 300 minutes"

echo "end to end: a legacy-only config is the baseline for the next write"
write_legacy_config 21 21 5
_t_blocks "a looser write against a legacy file is refused" \
	run_main 22:00 21:00 05:00
_t_allows "a stricter write against a legacy file succeeds" \
	run_main 20:30 20:30 05:00
_t_has "$(cat "$SHUTDOWN_CONFIG_FILE")" "MON_WED_MINUTES=1230" \
	"the legacy file is upgraded to minutes keys"

# --restore bypasses the stricter-only check on purpose: the workout reward
# pushes the schedule later than the base, so bounding it there would break a
# daily flow. The ceiling below is what bounds it.
write_config 1260 1260 300
_t_allows "--restore still loosens (deliberately unchanged)" \
	run_main --restore 23:00 23:00 05:00

echo "--restore ceiling (1380 = 23:00)"
_t_eq "1380" "$(clamp_restore 1440 Mon-Wed)" "clamps 24:00 down to the ceiling"
_t_eq "1380" "$(clamp_restore 1381 Mon-Wed)" "clamps even one minute past 23:00"
_t_eq "1380" "$(clamp_restore 1380 Mon-Wed)" "leaves the ceiling itself alone"
_t_eq "1110" "$(clamp_restore 1110 Mon-Wed)" "leaves an earlier time alone"
out="$(clamp_restore 1440 Mon-Wed 2>&1 >/dev/null)"
_t_has "$out" "clamped" "says so rather than clamping silently"

write_config 1260 1260 300
_t_allows "a restore above the ceiling still succeeds" \
	run_main --restore 24:00 24:00 05:00
body="$(cat "$SHUTDOWN_CONFIG_FILE")"
_t_has "$body" "MON_WED_MINUTES=1380" "the written value is the ceiling, not 1440"
_t_has "$body" "MON_WED_HOUR=23" "and its legacy hour copy is 23"
_t_has "$(cat "$SHUTDOWN_RESTORE_LOG")" "RESTORE" "the restore was recorded"
_t_has "$(cat "$SHUTDOWN_RESTORE_LOG")" "mon_wed=23:00" "in HH:MM"

write_config 1260 1260 300
run_main --restore 22:30 22:30 05:00 >/dev/null 2>&1
_t_has "$(cat "$SHUTDOWN_CONFIG_FILE")" "MON_WED_MINUTES=1350" \
	"a restore to 22:30 keeps its half hour"

# The overrides CONF is parsed by day-specific-shutdown-check.sh as
# start|end|created|reason, and a matching line makes it exit 0 and skip the
# shutdown. Audit lines must never go there.
_t_eq "0" "$(grep -c . "$TMP/shutdown-schedule-overrides.conf" 2>/dev/null || echo 0)" \
	"nothing was written to the overrides conf"

_t_summary
