#!/bin/bash
# Render assets/sounds/workout_done.wav (the finish-workout chime) from
# render_finish_chime.py with the PINNED music_theory toolkit, and rebuild
# its MANIFEST.json (recipe, toolkit version, SHA-256) from scratch.
#
# The pin matters: a moving toolkit HEAD would silently change the sound the
# user listened to. Re-running must reproduce the shipped bytes.
#
# Usage: tools/render_finish_chime.sh [output_dir]
# Requires: python3 (with venv), network access to github.com.
set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TOOLS_DIR
readonly TOOLKIT_SPEC="music_theory @ git+https://github.com/kuhyx/utils@music-theory-v0.1.0#subdirectory=music_theory"
readonly OUT_DIR="${1:-${TOOLS_DIR}/../assets/sounds}"
WORK_DIR=""

cleanup() {
	if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
		rm -rf "$WORK_DIR"
	fi
}
trap cleanup EXIT

main() {
	command -v python3 >/dev/null || { echo "Error: python3 is required" >&2; exit 1; }
	WORK_DIR="$(mktemp -d)"
	python3 -m venv "${WORK_DIR}/venv"
	"${WORK_DIR}/venv/bin/pip" install --quiet "$TOOLKIT_SPEC"
	"${WORK_DIR}/venv/bin/python" "${TOOLS_DIR}/render_finish_chime.py" "$OUT_DIR"
}

main "$@"
