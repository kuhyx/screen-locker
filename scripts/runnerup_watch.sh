#!/bin/bash

# ============================================================================
# Credit a RunnerUp run the moment its TCX upload lands on this machine.
#
# RunnerUp PUTs each export to dufs, which writes it straight into
# ~/data/cloud/RunnerUp: CREATE fires when the upload starts, CLOSE_WRITE when
# it ends. So this reacts to close_write/moved_to only -- a systemd .path unit
# (PathChanged=) fires on CREATE, hands the pass a half-written TCX and drops
# the close event while that pass runs, which left a 2026-10-07 run uncredited
# until the next timer tick.
#
# Each finished *.tcx starts workout-sync.service (blocking), which ingests it
# and applies the shutdown credit. systemd serialises that against the 15-min
# timer run; when one was already in flight it started before this file was
# complete, so the start merged into it and a second start is needed.
#
# Run by runnerup-watch.service (Restart=always). Event-driven: no polling.
# ============================================================================

set -euo pipefail

readonly WATCH_DIR="${RUNNERUP_WATCH_DIR:-$HOME/data/cloud/RunnerUp}"
readonly SYNC_UNIT="${RUNNERUP_SYNC_UNIT:-workout-sync.service}"

log() {
	printf '%s\n' "$*" >&2
}

start_sync() {
	if ! systemctl --user start "$SYNC_UNIT"; then
		log "WARNING: $SYNC_UNIT failed after a RunnerUp upload — the run" \
			"is NOT credited yet; see journalctl --user -u $SYNC_UNIT." \
			"The 15-min timer retries it."
		return 1
	fi
}

ingest() {
	local name="$1" state
	state="$(systemctl --user is-active "$SYNC_UNIT" || true)"
	log "RunnerUp upload finished: $name — starting $SYNC_UNIT"
	start_sync || return 0
	if [[ $state == activating ]]; then
		log "$SYNC_UNIT was already running when $name landed — running it again"
		start_sync || return 0
	fi
}

validate_requirements() {
	if ! command -v inotifywait >/dev/null 2>&1; then
		log "ERROR: inotifywait missing (pacman -S inotify-tools) — RunnerUp" \
			"uploads are only credited by the 15-min timer"
		exit 1
	fi
	if [[ ! -d $WATCH_DIR ]]; then
		log "ERROR: $WATCH_DIR does not exist — is dufs-cloud set up?" \
			"RunnerUp uploads are only credited by the 15-min timer"
		exit 1
	fi
}

main() {
	validate_requirements
	log "Watching $WATCH_DIR for finished RunnerUp TCX uploads"
	local name
	while IFS= read -r name; do
		[[ $name == *.tcx ]] || continue
		ingest "$name"
	done < <(inotifywait -m -q -e close_write -e moved_to --format '%f' "$WATCH_DIR")
	log "ERROR: inotifywait on $WATCH_DIR exited — restarting via systemd"
	exit 1
}

main "$@"
