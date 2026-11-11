#!/bin/bash
# Deploy screen-locker for real: update the live clone, reinstall, restart the
# long-running user units, prove they are healthy, then ship the workout app.
#
# Usage: bash scripts/deploy.sh [--health-only]
#
# Every path is anchored on the LIVE clone (~/src/screen-locker), never on this
# script's own directory: install.sh installs editable from wherever it sits,
# so running a worktree copy of it would point the services at scratch code.
#
# workout-locker.service is deliberately NOT restarted: it is the login-time
# gate and starting it can lock the display. Its timer is only re-enabled.
#
# Phone: phone_deploy.sh refuses com.kuhy.workout_app (exit 46) unless kuhy
# runs this himself with PHONE_PROTECT_ALLOW=com.kuhy.workout_app and the app
# closed. This script never sets that variable; it passes the caller's
# environment through and fails loudly when the guard refuses.
#
# Seams: SCREEN_LOCKER_LIVE (live clone), DEPLOY_WEB_PORT (health port).
# Exit: 0 healthy and installed everywhere | 1 any step or check failed.

set -euo pipefail

readonly LIVE="${SCREEN_LOCKER_LIVE:-$HOME/src/screen-locker}"
readonly PY="/usr/bin/python3"
readonly APP_DIR="stronglift_replacement/workout_app"
readonly PHONE_DEPLOY="$HOME/.claude/scripts/phone_deploy.sh"
readonly UNITS=(screen-locker-web.service workout-poke.service runnerup-watch.service)

die() { echo "deploy: FAIL: $*" >&2; exit 1; }
ok() { echo "deploy: ok: $*"; }

main_pid() { systemctl --user show -p MainPID --value "$1"; }

web_port() {
    if [[ -n "${DEPLOY_WEB_PORT:-}" ]]; then
        echo "$DEPLOY_WEB_PORT"
    else
        (cd /tmp && "$PY" -c 'from screen_locker._web_server import DEFAULT_PORT; print(DEFAULT_PORT)')
    fi
}

# /api/health answers and reports enforcement armed; retried while the
# freshly restarted server binds its port.
check_web() {
    local port body i
    port="$(web_port)"
    for i in $(seq 1 15); do
        if body="$(curl -fsS --max-time 2 "http://127.0.0.1:$port/api/health" 2>/dev/null)"; then
            jq -e '.armed == true' >/dev/null <<<"$body" \
                || die "web health on :$port says enforcement is NOT armed"
            ok "web /api/health on :$port armed (try $i)"
            return 0
        fi
        sleep 1
    done
    die "web /api/health on :$port did not answer within 15 s"
}

health() {
    local unit
    for unit in "${UNITS[@]}"; do
        systemctl --user is-active --quiet "$unit" || die "$unit is not active"
        ok "$unit active"
    done
    check_web
    "$PY" "$LIVE/scripts/check_enforcement_armed.py" --quiet \
        || die "check_enforcement_armed.py: enforcement is not armed"
    ok "enforcement armed"
    "$PY" "$LIVE/scripts/poke_selftest.py" sandbox >/dev/null \
        || die "workout-poke sandbox self-test failed"
    ok "workout-poke signed sandbox round trip"
    local mod
    mod="$(cd /tmp && "$PY" -c 'import screen_locker; print(screen_locker.__file__)')"
    [[ "$mod" == "$LIVE"/* ]] || die "screen_locker imports from $mod, not $LIVE"
    ok "screen_locker imports from the live clone"
}

desktop() {
    local unit
    declare -A before=()
    git -C "$LIVE" pull --ff-only || die "git pull --ff-only in $LIVE (dirty or diverged?)"
    [[ "$(git -C "$LIVE" rev-parse HEAD)" == "$(git -C "$LIVE" rev-parse '@{u}')" ]] \
        || die "$LIVE HEAD is not its upstream after the pull"
    ok "live clone at $(git -C "$LIVE" rev-parse --short HEAD)"
    bash "$LIVE/install.sh" || die "install.sh failed"
    for unit in "${UNITS[@]}"; do before[$unit]="$(main_pid "$unit")"; done
    systemctl --user restart "${UNITS[@]}" || die "restart of ${UNITS[*]} failed"
    for unit in "${UNITS[@]}"; do
        [[ "$(main_pid "$unit")" != "${before[$unit]}" ]] \
            || die "$unit kept PID ${before[$unit]}: restart did not take"
    done
    ok "restarted ${UNITS[*]}"
}

phone() {
    local rc=0
    bash "$PHONE_DEPLOY" "$LIVE/$APP_DIR" --release || rc=$?
    case "$rc" in
        0) ok "workout app release build installed on the phone" ;;
        46) die "phone_deploy protect guard (exit 46) refused com.kuhy.workout_app;" \
                "kuhy runs: PHONE_PROTECT_ALLOW=com.kuhy.workout_app bash $LIVE/scripts/deploy.sh" \
                "with the workout app closed" ;;
        *) die "phone_deploy.sh exited $rc (see its exit-code table)" ;;
    esac
}

if [[ "${1:-}" == "--health-only" ]]; then
    health
    exit 0
fi
desktop
health
phone
ok "deployed"
