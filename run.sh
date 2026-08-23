#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
# tkinter is from Python stdlib; install python-tk system package if missing:
#   Arch:   sudo pacman -S python-tk
#   Debian: sudo apt-get install python3-tk
cd "$SCRIPT_DIR"

if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
fi

# Reconcile the venv against requirements.txt whenever that file changes.
# Without this the venv is created once and never updated, so a dependency pin
# bump stays invisible until it surfaces as an ImportError at startup --
# crdt-sync sat at 0.6.0 for months after the pin moved to 0.9.0.
#
# Gated on a hash stamp so the common case costs nothing: pip re-resolves the
# git-pinned deps over the network (~5s) on every call, and this is a screen
# locker that must still start when the network is down.
STAMP="$VENV/.requirements.sha256"
WANT="$(sha256sum requirements.txt | cut -d" " -f1)"
HAVE="$(cat "$STAMP" 2>/dev/null || true)"

if [[ "$WANT" != "$HAVE" ]]; then
    echo "Dependencies changed; reconciling venv against requirements.txt..." >&2
    if "$VENV/bin/pip" install -q -r requirements.txt; then
        printf '%s\n' "$WANT" > "$STAMP"
    else
        # Do not stamp on failure, so the next launch retries. Abort rather
        # than run on dependencies we know are wrong.
        echo "ERROR: failed to install dependencies from requirements.txt" >&2
        echo "       Refusing to launch with unreconciled dependencies." >&2
        echo "       Retry manually: $VENV/bin/pip install -r requirements.txt" >&2
        exit 1
    fi
fi

exec "$VENV/bin/python" -m screen_locker.screen_lock "$@"
