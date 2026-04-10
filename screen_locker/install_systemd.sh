#!/bin/bash
# Install workout locker as a systemd user service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCREEN_LOCK_PATH="$SCRIPT_DIR/screen_lock.py"
SERVICE_FILE="$SCRIPT_DIR/workout-locker.service"
USER_SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="workout-locker.service"

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

# Copy service file to user systemd directory
cp "$SERVICE_FILE" "$USER_SERVICE_DIR/$SERVICE_NAME"

# Update paths in the service file to use absolute paths
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
sed -i "s|WorkingDirectory=.*|WorkingDirectory=$REPO_ROOT|" "$USER_SERVICE_DIR/$SERVICE_NAME"
sed -i "s|Environment=PYTHONPATH=.*|Environment=PYTHONPATH=$REPO_ROOT|" "$USER_SERVICE_DIR/$SERVICE_NAME"
sed -i "s|ExecStart=/usr/bin/python3.*|ExecStart=/usr/bin/python3 -m python_pkg.screen_locker.screen_lock --production|" "$USER_SERVICE_DIR/$SERVICE_NAME"

# Reload systemd daemon
systemctl --user daemon-reload

# Enable the service to start on login (one-shot, no periodic timer)
systemctl --user enable "$SERVICE_NAME"

echo "✓ Workout locker service installed"
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

I3_CONFIG="$HOME/.config/i3/config"
if [ -f "$I3_CONFIG" ] && grep -q "exec.*screen_lock.py" "$I3_CONFIG"; then
	echo "✓ i3 autostart: INSTALLED"
else
	echo "  i3 autostart: not installed"
	echo ""
	echo "To add i3 startup hook (recommended), add this line to $I3_CONFIG:"
	echo "  exec --no-startup-id /usr/bin/python3 -m python_pkg.screen_locker.screen_lock --production"
fi

# Immediately check if today's workout is done; block if not
echo ""
echo "=== Checking today's workout status ==="
python3 "$SCREEN_LOCK_PATH" --production
