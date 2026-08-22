#!/bin/bash
# ============================================================================
# Screen Locker installer: workout-to-unlock gate.
#
# Usage: bash install.sh
#
# Why this file exists
# --------------------
# It didn't, and that is exactly how the locker silently stopped working.
#
# Commit 9b420a9 (2026-06-22) removed `WorkingDirectory=/opt/screen-locker` and
# `Environment=PYTHONPATH=/opt/screen-locker` from workout-locker.service, on
# the correct-in-principle grounds that "screen_locker is now pip-installed".
# But nothing *guaranteed* that install: there was no installer, `/opt/screen-
# locker` no longer exists, and the package is absent from every Python
# version's user site-packages. So the unit lost its fallback path and gained a
# hard dependency on a manual step nobody re-ran.
#
# Result: workout-locker.service crash-looped with ModuleNotFoundError
# ~1977 times in a single boot while remaining `enabled`, and never started
# successfully. A locker that cannot start is a locker that does not lock.
#
# The fix is this script, not a reminder: run it and the install is real,
# editable (so `git pull` here reaches the running service), and verified
# against the *production* interpreter rather than a dev venv.
#
# What it does:
#   1. Checks system deps (setxkbmap, needed for the VT-disable)
#   2. pip-installs this package editable into system Python's USER
#      site-packages -- the service runs /usr/bin/python3 directly, not a venv
#   3. Installs + enables the systemd user units
#   4. Verifies the production interpreter can actually import the module,
#      and FAILS if it cannot (a warning here would just recreate the bug)
# ============================================================================

set -euo pipefail

# Split declare/assign so the command-substitution exit code is not masked.
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
readonly SCRIPT_DIR
readonly REPO_DIR="$SCRIPT_DIR"
readonly SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
readonly PROD_PYTHON="/usr/bin/python3"
# The shared lock backend, developed in lockstep with this repo.
readonly GATELOCK_DIR="$HOME/utils/gatelock"

echo "=== Screen Locker Installer ==="

# 1. System dependencies ------------------------------------------------------
echo "[1/4] Checking system dependencies..."
if ! command -v setxkbmap &>/dev/null; then
    echo "  installing xorg-setxkbmap (required to disable VT switching)..."
    sudo pacman -S --needed --noconfirm xorg-setxkbmap
else
    echo "  setxkbmap present."
fi

# 2. Install the package ------------------------------------------------------
# --break-system-packages is required on Arch (PEP 668). Editable so a later
# `git pull` in THIS clone updates the running service with no reinstall. That
# is also why the clone must live somewhere durable (~/screen-locker), never a
# scratch directory: a non-editable snapshot would freeze at this commit and
# silently stop tracking the repo.
echo "[2/4] Installing screen_locker into user site-packages (editable)..."
"$PROD_PYTHON" -m pip install --user --break-system-packages -e "$REPO_DIR"

# Re-assert an editable gatelock, deliberately AFTER the line above.
#
# pyproject.toml pins `gatelock @ git+https://.../@gatelock-v0.2.1`, so the
# install above resolves that pin and overwrites any local editable gatelock
# with a frozen wheel built from the tag. That silently reverts every
# unreleased change in ~/utils/gatelock and breaks the other lockers that
# depend on them -- observed: it removed `ScrollableSurface` and took
# diet_guard down with it.
#
# gatelock is a sibling in the utils monorepo and is developed in lockstep with
# the four lockers, so the local clone must win. Ordering is the fix: install
# it last.
if [[ -d "$GATELOCK_DIR" ]]; then
    echo "  re-asserting editable gatelock from $GATELOCK_DIR..."
    "$PROD_PYTHON" -m pip install --user --break-system-packages \
        --no-deps -e "$GATELOCK_DIR"
else
    echo "  WARNING: $GATELOCK_DIR not found; leaving the pinned gatelock" >&2
    echo "           wheel in place. Local gatelock changes will NOT be" >&2
    echo "           picked up by the running service." >&2
fi

# 3. systemd units ------------------------------------------------------------
# This step installs *and enables* every unit in the repo, which would clobber
# the systemd mask symlinks. Respect the disarm marker; ./arm.sh --rearm undoes.
# shellcheck source=scripts/disarm_guard.sh
source "$SCRIPT_DIR/scripts/disarm_guard.sh"
refuse_if_disarmed

echo "[3/4] Installing systemd user units..."
mkdir -p "$SYSTEMD_USER_DIR"
shopt -s nullglob
for unit in "$SCRIPT_DIR"/*.service "$SCRIPT_DIR"/*.timer; do
    install -m 644 "$unit" "$SYSTEMD_USER_DIR/$(basename "$unit")"
    echo "  installed $(basename "$unit")"
done
shopt -u nullglob
systemctl --user daemon-reload
for timer in "$SCRIPT_DIR"/*.timer; do
    [[ -e "$timer" ]] || continue
    systemctl --user enable --now "$(basename "$timer")"
    echo "  enabled $(basename "$timer")"
done

# 4. Verify the PRODUCTION import path ---------------------------------------
# This gates rather than warns. An installer that reports success while the
# service still cannot import the module is precisely the failure mode above,
# and a warning would be read as noise.
echo "[4/4] Verifying the production interpreter can import screen_locker..."
if ! (cd /tmp && "$PROD_PYTHON" -c "import screen_locker" 2>/dev/null); then
    echo "ERROR: $PROD_PYTHON cannot import screen_locker after install." >&2
    echo "       The systemd service uses this interpreter, so it would" >&2
    echo "       crash-loop with ModuleNotFoundError. Refusing to report" >&2
    echo "       success." >&2
    exit 1
fi
if ! (cd /tmp && "$PROD_PYTHON" -c "import gatelock" 2>/dev/null); then
    echo "ERROR: $PROD_PYTHON cannot import gatelock (the shared lock" >&2
    echo "       backend). Install it editable from ~/utils/gatelock." >&2
    exit 1
fi
if [[ -d "$GATELOCK_DIR" ]]; then
    gatelock_path="$(cd /tmp && "$PROD_PYTHON" -c \
        "import gatelock; print(gatelock.__file__)")"
    if [[ "$gatelock_path" != "$GATELOCK_DIR"* ]]; then
        echo "ERROR: gatelock resolves to $gatelock_path, not the local" >&2
        echo "       clone at $GATELOCK_DIR. The pinned wheel won, so local" >&2
        echo "       gatelock changes would not reach the service." >&2
        exit 1
    fi
    echo "  ok: gatelock resolves to the local editable clone"
fi
echo "  ok: screen_locker and gatelock both import under $PROD_PYTHON"

echo
echo "=== Done ==="
echo "The locker is live. Check when it next fires with:"
echo "  systemctl --user list-timers | grep -i workout"
