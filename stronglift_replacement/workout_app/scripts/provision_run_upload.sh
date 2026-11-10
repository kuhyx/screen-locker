#!/bin/bash
# provision_run_upload.sh — give the workout app its own dufs login for run
# uploads, without anyone typing a password.
#
#   1. creates (idempotently) a dufs login `workout_app` scoped `/RunnerUp rw`
#      via ~/src/dufs-cloud/scripts/add_dufs_login.sh. That script needs sudo
#      (it restarts dufs.service the first time, and may `pacman -S` openssl/
#      curl/xclip); an existing login is left alone. It never touches the
#      `runnerup` login the stock RunnerUp app depends on, and this script
#      never passes --rotate.
#   2. writes {"url","user","password"} (url = the BARE origin, the app
#      appends /RunnerUp/<file>) to a 0600 temp file,
#   3. adb-pushes it to the app's external files dir, where the app imports it
#      into secure storage on the next start and deletes it.
#
# The app uploads each finished run as a TCX; a PC-side watcher credits it.
# Run only when the phone is attached and the app has been started once.
#
# Usage: provision_run_upload.sh [--print-only]
#   ADB_SERIAL  phone serial (default 23181JEGR08034)

set -euo pipefail

readonly LOGIN_USER="workout_app"
readonly LOGIN_PATH="/RunnerUp"
readonly ADD_LOGIN="${ADD_DUFS_LOGIN:-${HOME}/src/dufs-cloud/scripts/add_dufs_login.sh}"
readonly ENV_FILE="${DUFS_LOGINS_DIR:-${HOME}/.config/dufs/logins}/${LOGIN_USER}.env"
readonly SERIAL="${ADB_SERIAL:-23181JEGR08034}"
readonly APP_ID="com.kuhy.workout_app"
readonly REMOTE_DIR="/sdcard/Android/data/${APP_ID}/files"
readonly REMOTE_FILE="${REMOTE_DIR}/dufs_login.json"

PRINT_ONLY=0
TMP_JSON=""

die() {
	printf '[FAIL] %s\n' "$*" >&2
	exit 1
}

cleanup() {
	if [[ -n ${TMP_JSON} && -f ${TMP_JSON} ]]; then
		rm -f "${TMP_JSON}"
	fi
}
trap cleanup EXIT

# Reads KEY from the login's .env without sourcing it (no code execution).
env_value() {
	local key="$1" line
	line="$(grep -m1 "^${key}=" "${ENV_FILE}")" || die "${key} missing in ${ENV_FILE}"
	printf '%s' "${line#*=}"
}

check_tools() {
	local tool
	for tool in jq adb; do
		command -v "${tool}" >/dev/null || die "${tool} is required (sudo pacman -S ${tool})"
	done
	[[ -x ${ADD_LOGIN} ]] || die "missing ${ADD_LOGIN}"
}

ensure_login() {
	"${ADD_LOGIN}" "${LOGIN_USER}" "${LOGIN_PATH}" rw
	[[ -f ${ENV_FILE} ]] || die "${ENV_FILE} was not written"
}

write_json() {
	TMP_JSON="$(mktemp)"
	chmod 600 "${TMP_JSON}"
	jq -n \
		--arg url "$(env_value DUFS_URL)" \
		--arg user "$(env_value DUFS_USER)" \
		--arg password "$(env_value DUFS_PASSWORD)" \
		'{url: $url, user: $user, password: $password}' >"${TMP_JSON}"
	jq -e '.url | test("^https?://[^/]+$")' "${TMP_JSON}" >/dev/null ||
		die "url must be a bare origin without a path"
}

push_json() {
	adb -s "${SERIAL}" get-state >/dev/null || die "phone ${SERIAL} is not attached"
	adb -s "${SERIAL}" shell mkdir -p "${REMOTE_DIR}"
	adb -s "${SERIAL}" push "${TMP_JSON}" "${REMOTE_FILE}" >/dev/null
	adb -s "${SERIAL}" shell ls -l "${REMOTE_FILE}"
	printf '[ OK ] pushed; open the app once: it imports the login and deletes the file\n'
}

main() {
	if [[ ${1:-} == --print-only ]]; then
		PRINT_ONLY=1
	elif [[ $# -gt 0 ]]; then
		die "usage: provision_run_upload.sh [--print-only]"
	fi
	check_tools
	# --print-only must not need sudo: reuse an existing login's .env.
	if [[ ${PRINT_ONLY} -eq 0 || ! -f ${ENV_FILE} ]]; then
		ensure_login
	fi
	write_json
	if [[ ${PRINT_ONLY} -eq 1 ]]; then
		jq '.password = "***"' "${TMP_JSON}"
		return 0
	fi
	push_json
}

main "$@"
