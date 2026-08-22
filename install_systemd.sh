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

# Immediately check if today's workout is done; block if not
echo ""
echo "=== Checking today's workout status ==="
PYTHONPATH="$SCRIPT_DIR" python3 -m screen_locker.screen_lock --production
