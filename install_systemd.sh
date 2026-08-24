#!/bin/bash
# Install workout locker as a systemd user service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/workout-locker.service"
EARLY_BIRD_TIMER_FILE="$SCRIPT_DIR/early-bird-workout-check.timer"
LOCKER_TIMER_FILE="$SCRIPT_DIR/workout-locker.timer"
SYNC_SERVICE_FILE="$SCRIPT_DIR/workout-sync.service"
SYNC_TIMER_FILE="$SCRIPT_DIR/workout-sync.timer"
USER_SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="workout-locker.service"
EARLY_BIRD_TIMER_NAME="early-bird-workout-check.timer"
LOCKER_TIMER_NAME="workout-locker.timer"
SYNC_SERVICE_NAME="workout-sync.service"
SYNC_TIMER_NAME="workout-sync.timer"

# Runtime dependencies. screen_lock.py imports tkinter at module scope. On Arch
# the tkinter MODULE ships inside the `python` package, but the shared library
# it dlopens does not: without `tk` the import dies with
# "ImportError: libtk8.6.so: cannot open shared object file" and this installer
# exits 1. That is exactly how a fresh Arch box behaves, since `tk` is only an
# optional dependency of python. Install it rather than documenting it: a fresh
# install must not require the user to know this.
ensure_runtime_deps() {
	if ! python3 -c 'import tkinter' 2>/dev/null; then
		if command -v pacman >/dev/null 2>&1; then
			echo "Installing missing system dependency: tk"
			if [ "$(id -u)" -eq 0 ]; then
				pacman -S --needed --noconfirm tk
			else
				sudo pacman -S --needed --noconfirm tk
			fi
		else
			echo "WARNING: tkinter missing and pacman unavailable - install tk manually" >&2
		fi
	fi

	# The two shared RUNTIME dependencies, both pinned git deps in
	# pyproject.toml: gatelock (lock-window/HMAC backend) and crdt-sync (the
	# workout-sync transport). Nothing here used to install either, so a fresh
	# checkout died with "ModuleNotFoundError: No module named 'gatelock'" the
	# first time the post-install workout check ran, and with crdt_sync right
	# after that. requirements.txt is NOT used here on purpose: it also pins the
	# dev toolchain (pytest, mypy, ruff...), which a fresh install does not need.
	#
	# Arch marks its system Python externally-managed, so a plain `pip install`
	# refuses; --break-system-packages is what the sibling installers already use.
	_pip_runtime_dep() { # <import-name> <pip-spec>
		python3 -c "import $1" 2>/dev/null && return 0
		echo "Installing missing Python dependency: $1"
		pip3 install --user --quiet "$2" 2>/dev/null ||
			pip3 install --user --break-system-packages --quiet "$2" ||
			echo "WARNING: could not install $1 automatically" >&2
	}
	_pip_runtime_dep gatelock \
		"gatelock @ git+https://github.com/kuhyx/utils@gatelock-v0.7.1#subdirectory=gatelock"
	_pip_runtime_dep crdt_sync \
		"crdt-sync @ git+https://github.com/kuhyx/utils@crdt-sync-v0.9.0#subdirectory=crdt-sync"
}
ensure_runtime_deps

# shellcheck source=scripts/disarm_guard.sh
source "$SCRIPT_DIR/scripts/disarm_guard.sh"
# Installing units here would overwrite the systemd mask symlinks, so this
# path has to respect the disarm marker too. Re-arm via: ./arm.sh --rearm
refuse_if_disarmed

# Check if service is already installed
if [ -f "$USER_SERVICE_DIR/$SERVICE_NAME" ]; then
	echo "Screen locker systemd service is already installed."
	echo "Current status:"
	systemctl --user status "$SERVICE_NAME" --no-pager || true
	echo ""
	read -p "Do you want to reinstall/update it? (y/n) " -n 1 -r
	echo
	if [[ ! $REPLY =~ ^[Yy]$ ]]; then
		echo "Keeping existing installation"
		exit 0
	fi
fi

# Create user systemd directory if it doesn't exist
mkdir -p "$USER_SERVICE_DIR"

# Remove old timer if it was previously installed
if systemctl --user is-active "workout-locker.timer" &>/dev/null; then
	systemctl --user disable --now "workout-locker.timer" 2>/dev/null || true
fi
rm -f "$USER_SERVICE_DIR/workout-locker.timer"

# Seed shutdown_base.json with base=21 if not already present
SHUTDOWN_BASE="$SCRIPT_DIR/screen_locker/shutdown_base.json"
if [[ ! -f "$SHUTDOWN_BASE" ]]; then
	printf '{\n  "base_mon_wed_hour": 21,\n  "base_thu_sun_hour": 21,\n  "last_reset_date": ""\n}\n' > "$SHUTDOWN_BASE"
	echo "✓ Created shutdown_base.json with base=21:00"
fi

# Copy service file to user systemd directory
cp "$SERVICE_FILE" "$USER_SERVICE_DIR/$SERVICE_NAME"

# Copy early bird timer
cp "$EARLY_BIRD_TIMER_FILE" "$USER_SERVICE_DIR/$EARLY_BIRD_TIMER_NAME"

# Copy the periodic re-check timer. Without it the locker only ever decides at
# login and at 08:30/09:05, so a day or ISO-week boundary crossed inside a long
# session is never re-evaluated.
cp "$LOCKER_TIMER_FILE" "$USER_SERVICE_DIR/$LOCKER_TIMER_NAME"

# Copy the periodic workout-sync units. Without these, syncing happens only
# once per locker start, so a workout finished after login is not seen until
# the next login.
cp "$SYNC_SERVICE_FILE" "$USER_SERVICE_DIR/$SYNC_SERVICE_NAME"
cp "$SYNC_TIMER_FILE" "$USER_SERVICE_DIR/$SYNC_TIMER_NAME"

# Update paths in the service file to use absolute paths
REPO_ROOT="$SCRIPT_DIR"
sed -i "s|WorkingDirectory=.*|WorkingDirectory=$REPO_ROOT|" "$USER_SERVICE_DIR/$SERVICE_NAME"
sed -i "s|Environment=PYTHONPATH=.*|Environment=PYTHONPATH=$REPO_ROOT|" "$USER_SERVICE_DIR/$SERVICE_NAME"
sed -i "s|ExecStart=/usr/bin/python3.*|ExecStart=/usr/bin/python3 -m screen_locker.screen_lock --production|" "$USER_SERVICE_DIR/$SERVICE_NAME"

# Reload systemd daemon
systemctl --user daemon-reload

# Enable the service to start on login (one-shot, no periodic timer)
systemctl --user enable "$SERVICE_NAME"

# Enable the early bird re-check timer
systemctl --user enable --now "$EARLY_BIRD_TIMER_NAME"

# Enable the periodic re-check timer
systemctl --user enable --now "$LOCKER_TIMER_NAME"

# Enable the periodic workout sync
systemctl --user enable --now "$SYNC_TIMER_NAME"

# Verify enforcement is actually armed. enable can silently no-op when systemd
# breaks an ordering cycle by deleting the timer's job -- exactly what happened
# on 2026-08-04 -- so a successful `enable` is NOT proof the locker will run.
if ! python3 "$SCRIPT_DIR/scripts/check_enforcement_armed.py"; then
	echo "✗ Enforcement is NOT armed after install — see the errors above" >&2
	exit 1
fi

echo "✓ Workout locker service installed"
echo "✓ Early bird re-check timer installed (fires daily at 08:30)"
echo "✓ Periodic re-check timer installed (every 30 min)"
echo "✓ Service will start automatically on next login"
echo ""
echo "To start now: systemctl --user start workout-locker"
echo "To check status: systemctl --user status workout-locker"
echo "To stop: systemctl --user stop workout-locker"
echo "To disable autostart: systemctl --user disable workout-locker"

# Check autostart installation status
echo ""
echo "=== Autostart Status ==="
if systemctl --user is-enabled "$SERVICE_NAME" &>/dev/null; then
	echo "✓ systemd service: INSTALLED and enabled"
else
	echo "✗ systemd service: NOT enabled"
fi
if systemctl --user is-enabled "$EARLY_BIRD_TIMER_NAME" &>/dev/null; then
	echo "✓ early bird timer: INSTALLED and enabled"
else
	echo "✗ early bird timer: NOT enabled"
fi
if systemctl --user is-enabled "$SYNC_TIMER_NAME" &>/dev/null; then
	echo "✓ workout sync timer: INSTALLED and enabled (every 15 min)"
else
	echo "✗ workout sync timer: NOT enabled"
fi

I3_CONFIG="$HOME/.config/i3/config"
if [ -f "$I3_CONFIG" ] && grep -q "exec.*screen_lock.py" "$I3_CONFIG"; then
	echo "✓ i3 autostart: INSTALLED"
else
	echo "  i3 autostart: not installed"
	echo ""
	echo "To add i3 startup hook (recommended), add this line to $I3_CONFIG:"
	echo "  exec --no-startup-id /usr/bin/python3 -m screen_locker.screen_lock --production"
fi

# Immediately check if today's workout is done; block if not.
#
# --production builds the real Tk UI and, when today is non-compliant, GRABS
# THE SCREEN and waits for a workout to be logged. That is correct for an
# interactive install, but it never returns on its own -- so when this script
# is driven non-interactively (install_core_system.sh, CI, `vm run`) the whole
# installer hangs forever on its last line. Only take the blocking path when
# there is a terminal to answer it; otherwise report status and exit.
# SCREEN_LOCKER_ENFORCE_AFTER_INSTALL=1 forces the blocking check.
echo ""
echo "=== Checking today's workout status ==="
if [ -t 0 ] || [ "${SCREEN_LOCKER_ENFORCE_AFTER_INSTALL:-0}" = "1" ]; then
	PYTHONPATH="$SCRIPT_DIR" python3 -m screen_locker.screen_lock --production
else
	echo "(non-interactive install: reporting status instead of enforcing)"
	PYTHONPATH="$SCRIPT_DIR" python3 -m screen_locker.screen_lock --status || true
	echo "Enforcement is armed via the systemd units installed above."
fi
