#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
[[ ! -d "$VENV" ]] && python3 -m venv "$VENV"
# tkinter is from Python stdlib; install python-tk system package if missing:
#   Arch:   sudo pacman -S python-tk
#   Debian: sudo apt-get install python3-tk
cd "$SCRIPT_DIR"
"$VENV/bin/python" -m screen_locker.screen_lock "$@"
