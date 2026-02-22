#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV="$REPO_ROOT/.venv"
[[ ! -d "$VENV" ]] && python3 -m venv "$VENV"
# tkinter is from Python stdlib; install python-tk system package if missing:
#   Arch:   sudo pacman -S python-tk
#   Debian: sudo apt-get install python3-tk
"$VENV/bin/python" "$SCRIPT_DIR/screen_lock.py" "$@"
