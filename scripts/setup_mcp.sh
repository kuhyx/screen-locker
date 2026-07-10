#!/bin/bash

# ============================================================================
# Set up the dedicated virtualenv that hosts the screen-locker MCP server.
# Claude Code spawns this interpreter (see the repo-root .mcp.json) to run
# `python -m screen_locker._mcp` over stdio.
#
# The MCP SDK (`mcp`) lives ONLY in this venv — it is an optional dependency,
# deliberately kept out of the system/CLI/systemd python path. Both `mcp` and
# `screen_locker` must be importable by this one interpreter or the MCP server
# fails to start silently.
#
# The server is READ-ONLY: it exposes status/query tools only, never any tool
# that logs a workout or mutates state.
#
# Idempotent: safe to re-run to pick up dependency changes.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly SCRIPT_DIR REPO_DIR
readonly VENV_DIR="${HOME}/.venvs/screen-locker-mcp"

main() {
    echo "== Setting up MCP venv at ${VENV_DIR} =="

    if [[ ! -d "${VENV_DIR}" ]]; then
        python3 -m venv "${VENV_DIR}"
    fi

    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet -e "${REPO_DIR}[mcp]"

    echo "== Verifying imports =="
    "${VENV_DIR}/bin/python" -c \
        "import mcp, screen_locker; print('mcp + screen_locker import OK')"

    echo
    echo "Done. The server is registered via ${REPO_DIR}/.mcp.json"
    echo "Restart Claude Code in this repo and approve the project MCP server prompt."
}

main "$@"
