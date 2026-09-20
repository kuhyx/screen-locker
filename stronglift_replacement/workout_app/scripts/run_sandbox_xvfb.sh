#!/bin/bash

# ============================================================================
# Run the workout app's Linux build as the SANDBOX on a virtual display.
#
# For checking a change on the PC before the phone: the app runs under Xvfb
# (never the live display), with an isolated HOME so the PC's real workout
# state is untouched, WORKOUT_SANDBOX=1 (offline, short rests, red ribbon),
# and its window sized to the phone's logical 411x914.
#
# Usage:
#   run_sandbox_xvfb.sh start            # build must exist (flutter build linux --debug)
#   run_sandbox_xvfb.sh shot <out.png>   # screenshot the virtual display
#   run_sandbox_xvfb.sh tap <x> <y>      # click at window-relative logical coords
#   run_sandbox_xvfb.sh log              # tail the app's stdout (the sandbox trace)
#   run_sandbox_xvfb.sh stop
#
# Requires: Xvfb, xdotool, scrot (all in pacman).
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly APP_DIR
readonly STATE_DIR="${WORKOUT_SANDBOX_XVFB_DIR:-/tmp/workout_sandbox_xvfb}"
readonly BUNDLE="$APP_DIR/build/linux/x64/debug/bundle/workout_app"
readonly PHONE_W=411
readonly PHONE_H=914
readonly DISPLAY_NUM="${WORKOUT_SANDBOX_DISPLAY:-:97}"

usage() {
    sed -n '/^# Usage:/,/^# Requires/p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
}

require() {
    command -v "$1" >/dev/null || { echo "$SCRIPT_NAME: missing $1 (pacman -S ${2:-$1})" >&2; exit 1; }
}

window_id() {
    # The toplevel is named "workout_app"; the GTK app id (com.kuhy.workout_app)
    # is its class, shared with a 10x10 helper window, so match on the name.
    DISPLAY="$DISPLAY_NUM" xdotool search --onlyvisible --name '^workout_app$' 2>/dev/null | head -1
}

start() {
    require Xvfb xorg-server-xvfb; require xdotool; require scrot
    [[ -x "$BUNDLE" ]] || { echo "$SCRIPT_NAME: no Linux build at $BUNDLE — run: flutter build linux --debug" >&2; exit 1; }
    mkdir -p "$STATE_DIR/home"
    Xvfb "$DISPLAY_NUM" -screen 0 "${PHONE_W}x${PHONE_H}x24" > "$STATE_DIR/xvfb.log" 2>&1 &
    echo $! > "$STATE_DIR/xvfb.pid"
    sleep 1
    # Isolated HOME: the app resolves its documents dir from it, so the
    # sandbox's SQLite lands under $STATE_DIR/home, never in ~/.local/share.
    HOME="$STATE_DIR/home" XDG_DATA_HOME="$STATE_DIR/home/.local/share" \
        XDG_CONFIG_HOME="$STATE_DIR/home/.config" DISPLAY="$DISPLAY_NUM" \
        WORKOUT_SANDBOX=1 "$BUNDLE" > "$STATE_DIR/app.log" 2>&1 &
    echo $! > "$STATE_DIR/app.pid"
    local wid=""
    for _ in $(seq 1 30); do
        wid=$(window_id) && [[ -n "$wid" ]] && break
        sleep 0.5
    done
    [[ -n "$wid" ]] || { echo "$SCRIPT_NAME: app window never appeared; see $STATE_DIR/app.log" >&2; stop; exit 1; }
    DISPLAY="$DISPLAY_NUM" xdotool windowmove "$wid" 0 0 windowsize "$wid" "$PHONE_W" "$PHONE_H"
    sleep 1
    echo "sandbox up on $DISPLAY_NUM (window $wid, ${PHONE_W}x${PHONE_H}); trace: $STATE_DIR/app.log"
}

shot() {
    local out="${1:?shot needs an output path}"
    DISPLAY="$DISPLAY_NUM" scrot -o "$out"
    echo "wrote $out"
}

tap() {
    local x="${1:?tap needs x}" y="${2:?tap needs y}"
    DISPLAY="$DISPLAY_NUM" xdotool mousemove "$x" "$y" click 1
    sleep 0.5
}

stop() {
    local f
    for f in app xvfb; do
        if [[ -f "$STATE_DIR/$f.pid" ]]; then
            kill "$(cat "$STATE_DIR/$f.pid")" 2>/dev/null || true
            rm -f "$STATE_DIR/$f.pid"
        fi
    done
    echo "stopped (data kept in $STATE_DIR/home; rm -rf it for a fresh sandbox)"
}

case "${1:-}" in
    start) start ;;
    shot) shot "${2:-}" ;;
    tap) tap "${2:-}" "${3:-}" ;;
    log) tail -n "${2:-40}" "$STATE_DIR/app.log" ;;
    stop) stop ;;
    *) usage ;;
esac
