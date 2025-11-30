#!/bin/bash
# Remove workout locker systemd service

SERVICE_NAME="workout-locker.service"
USER_SERVICE_DIR="$HOME/.config/systemd/user"

# Stop the service if running
systemctl --user stop "$SERVICE_NAME" 2>/dev/null

# Disable the service
systemctl --user disable "$SERVICE_NAME" 2>/dev/null

# Remove service file
rm -f "$USER_SERVICE_DIR/$SERVICE_NAME"

# Reload systemd daemon
systemctl --user daemon-reload

echo "✓ Workout locker service removed"
