#!/usr/bin/env bash
# Shared harness for the adjust_shutdown_schedule.sh tests (sourced, not run).
#
# This ratchet had no test at all, which is how the morning end went unchecked
# for months while the two evening times were guarded. The direction cases
# below are the point of the file: "stricter" means SMALLER for the evening
# times and LARGER for the morning end. Times are minutes after midnight; the
# config also carries strict-rounded *_HOUR copies for pre-minutes readers.
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

# A config as written since the minutes migration: authoritative *_MINUTES.
write_config() {
	cat >"$SHUTDOWN_CONFIG_FILE" <<EOF
MON_WED_MINUTES=$1
THU_SUN_MINUTES=$2
MORNING_END_MINUTES=$3
EOF
}

# A config as written before it: whole-hour keys only.
write_legacy_config() {
	cat >"$SHUTDOWN_CONFIG_FILE" <<EOF
MON_WED_HOUR=$1
THU_SUN_HOUR=$2
MORNING_END_HOUR=$3
EOF
}

# shellcheck source=/dev/null
source "$TARGET"

# Run main in a subshell; the allow/block helpers only need its exit status.
run_main() { (main "$@"); }


_t_summary() {
	echo
	printf 'passed: %d, failed: %d\n' "$PASS" "$FAIL"
	[[ $FAIL -eq 0 ]]
}
