#!/bin/bash
# Install workout locker as a systemd user service

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_FILE="$SCRIPT_DIR/workout-locker.service"
USER_SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="workout-locker.service"

# Create user systemd directory if it doesn't exist
mkdir -p "$USER_SERVICE_DIR"

# Copy service file to user systemd directory
cp "$SERVICE_FILE" "$USER_SERVICE_DIR/$SERVICE_NAME"

# Update the ExecStart path in the service file to use absolute path
sed -i "s|ExecStart=/usr/bin/python3.*|ExecStart=/usr/bin/python3 $SCRIPT_DIR/screen_lock.py|" "$USER_SERVICE_DIR/$SERVICE_NAME"

# Reload systemd daemon
systemctl --user daemon-reload

# Enable the service to start on login
systemctl --user enable "$SERVICE_NAME"

echo "✓ Workout locker service installed"
echo "✓ Service will start automatically on next login"
echo ""
echo "To start now: systemctl --user start workout-locker"
echo "To check status: systemctl --user status workout-locker"
echo "To stop: systemctl --user stop workout-locker"
echo "To disable autostart: systemctl --user disable workout-locker"
