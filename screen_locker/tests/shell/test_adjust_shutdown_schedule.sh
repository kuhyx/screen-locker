#!/usr/bin/env bash
# Tests for the shutdown-schedule ratchet.
#
# This ratchet had no test at all, which is how MORNING_END_HOUR went
# unchecked for months while the two evening hours were guarded. The direction
# cases below are the point of the file: "stricter" means SMALLER for the
# evening hours and LARGER for the morning end.
#
# Nothing here touches /etc: SHUTDOWN_CONFIG_FILE points at a tmpdir, and
# chattr/guardctl are shimmed on PATH because chattr cannot mark a file
# immutable on tmpfs and would abort the write.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly TARGET="${SCRIPT_DIR}/../../adjust_shutdown_schedule.sh"

PASS=0
FAIL=0

_t_pass() {
	PASS=$((PASS + 1))
	printf '  OK: %s\n' "$1"
}

_t_fail() {
	FAIL=$((FAIL + 1))
	printf '  FAIL: %s\n' "$1"
}

# The ratchet returns 0 to allow a write and 1 to block it. Which way it fails
# is the entire point, so assert on the exit status explicitly.
_t_allows() {
	local what="$1"
	shift
	if "$@" >/dev/null 2>&1; then
		_t_pass "$what"
	else
		_t_fail "$what (blocked when it should have allowed)"
	fi
}

_t_blocks() {
	local what="$1"
	shift
	if "$@" >/dev/null 2>&1; then
		_t_fail "$what (allowed when it should have blocked)"
	else
		_t_pass "$what"
	fi
}

_t_eq() {
	local want="$1" got="$2" what="$3"
	if [[ "$got" == "$want" ]]; then
		_t_pass "$what"
	else
		_t_fail "$what (want '${want}', got '${got}')"
	fi
}

_t_has() {
	local haystack="$1" needle="$2" what="$3"
	if [[ "$haystack" == *"$needle"* ]]; then
		_t_pass "$what"
	else
		_t_fail "$what (want substring '${needle}')"
	fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Shim the two commands that need root or a real filesystem.
mkdir -p "$TMP/bin"
cat >"$TMP/bin/chattr" <<'EOF'
#!/bin/bash
exit 0
EOF
cat >"$TMP/bin/guardctl" <<'EOF'
#!/bin/bash
printf '%s' "${FAKE_CANONICAL:-}"
EOF
chmod +x "$TMP/bin/chattr" "$TMP/bin/guardctl"
export PATH="$TMP/bin:$PATH"

export SHUTDOWN_CONFIG_FILE="$TMP/shutdown-schedule.conf"
export SHUTDOWN_RESTORE_LOG="$TMP/restore.log"
export FAKE_CANONICAL="$TMP/canonical"

write_config() {
	cat >"$SHUTDOWN_CONFIG_FILE" <<EOF
MON_WED_HOUR=$1
THU_SUN_HOUR=$2
MORNING_END_HOUR=$3
EOF
}

# shellcheck source=/dev/null
source "$TARGET"

echo "validate_hours"
_t_allows "accepts 0 and 23" validate_hours 0 23 5
_t_blocks "rejects a non-integer" validate_hours 21 abc 5
_t_blocks "rejects a negative (the minus makes it non-numeric)" \
	validate_hours -1 21 5

echo "check_stricter_only: evening hours (smaller is stricter)"
write_config 23 23 5
_t_allows "allows an earlier Mon-Wed" check_stricter_only 21 23 5
_t_allows "allows an unchanged schedule" check_stricter_only 23 23 5
_t_blocks "blocks a later Mon-Wed" check_stricter_only 24 23 5
_t_blocks "blocks a later Thu-Sun" check_stricter_only 23 24 5

echo "check_stricter_only: morning end (LARGER is stricter -- inverted)"
write_config 23 23 5
_t_allows "allows a later morning end, which lengthens the window" \
	check_stricter_only 23 23 7
_t_blocks "blocks an earlier morning end, which shortens the window" \
	check_stricter_only 23 23 3
out="$(check_stricter_only 23 23 3 2>&1 || true)"
_t_has "$out" "shortens the" "explains WHY the morning end was rejected"

echo "check_stricter_only: the source-clobber trap"
# `source` overwrites MON_WED_HOUR et al with the OLD values. If the comparison
# read those globals instead of its arguments it would compare a value with
# itself and pass everything.
write_config 21 21 5
_t_blocks "still blocks a loosening after source has clobbered the globals" \
	check_stricter_only 23 23 5

echo "check_stricter_only: missing or unreadable config"
rm -f "$SHUTDOWN_CONFIG_FILE"
_t_allows "allows any write when no config exists yet" check_stricter_only 23 23 0
printf 'garbage not a config\n' >"$SHUTDOWN_CONFIG_FILE"
_t_allows "falls back to the loosest defaults rather than rejecting" \
	check_stricter_only 23 23 0

echo "end to end"
write_config 23 23 5
if (main 21 21 5 >/dev/null 2>&1); then
	_t_pass "a stricter write succeeds"
else
	_t_fail "a stricter write succeeds"
fi
_t_has "$(cat "$SHUTDOWN_CONFIG_FILE")" "MON_WED_HOUR=21" "config was rewritten"
_t_has "$(cat "$FAKE_CANONICAL")" "MON_WED_HOUR=21" "canonical copy was written too"

write_config 21 21 5
if (main 23 23 5 >/dev/null 2>&1); then
	_t_fail "a looser write is refused"
else
	_t_pass "a looser write is refused"
fi
_t_has "$(cat "$SHUTDOWN_CONFIG_FILE")" "MON_WED_HOUR=21" "config was left untouched"

# --restore still bypasses the ratchet on purpose: the workout reward pushes the
# schedule later than shutdown_base.json, so bounding it here would break a
# daily flow. Bounding it is a separate, open decision.
write_config 21 21 5
if (main --restore 23 23 5 >/dev/null 2>&1); then
	_t_pass "--restore still loosens (deliberately unchanged)"
else
	_t_fail "--restore still loosens (deliberately unchanged)"
fi

echo "validate_hours: 24 means midnight"
# _shutdown.py's extra-workout bonus caps at 24 deliberately, and
# day-specific-shutdown-check.sh catches it via the morning window. Rejecting
# 24 would break that path; the old 0-23 error message was what was wrong.
_t_allows "accepts 24 (midnight), which the bonus path relies on" \
	validate_hours 24 24 5
_t_blocks "still rejects 25" validate_hours 25 21 5

echo "--restore ceiling"
_t_eq "23" "$(clamp_restore 24 Mon-Wed)" "clamps 24 down to the ceiling"
_t_eq "23" "$(clamp_restore 23 Mon-Wed)" "leaves the ceiling itself alone"
_t_eq "21" "$(clamp_restore 21 Mon-Wed)" "leaves an earlier hour alone"
out="$(clamp_restore 24 Mon-Wed 2>&1 >/dev/null)"
_t_has "$out" "clamped" "says so rather than clamping silently"

write_config 21 21 5
if (main --restore 24 24 5 >/dev/null 2>&1); then
	_t_pass "a restore above the ceiling still succeeds"
else
	_t_fail "a restore above the ceiling still succeeds"
fi
_t_has "$(cat "$SHUTDOWN_CONFIG_FILE")" "MON_WED_HOUR=23" \
	"the written value is the ceiling, not 24"
_t_has "$(cat "$SHUTDOWN_RESTORE_LOG")" "RESTORE" "the restore was recorded"

# The overrides CONF is parsed by day-specific-shutdown-check.sh as
# start|end|created|reason, and a matching line makes it exit 0 and skip the
# shutdown. Audit lines must never go there.
_t_eq "0" "$(grep -c . "$TMP/shutdown-schedule-overrides.conf" 2>/dev/null || echo 0)" \
	"nothing was written to the overrides conf"

echo
printf 'passed: %d, failed: %d\n' "$PASS" "$FAIL"
[[ $FAIL -eq 0 ]]
