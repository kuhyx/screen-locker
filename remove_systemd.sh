#!/bin/bash
# Remove workout locker systemd service

SERVICE_NAME="workout-locker.service"
TIMER_NAME="workout-locker.timer"
USER_SERVICE_DIR="$HOME/.config/systemd/user"

# Stop the service and timer if running
systemctl --user stop "$TIMER_NAME" 2>/dev/null
systemctl --user stop "$SERVICE_NAME" 2>/dev/null

# Disable the service and timer
systemctl --user disable "$TIMER_NAME" 2>/dev/null
systemctl --user disable "$SERVICE_NAME" 2>/dev/null

# Remove service and timer files
rm -f "$USER_SERVICE_DIR/$SERVICE_NAME"
rm -f "$USER_SERVICE_DIR/$TIMER_NAME"

# Reload systemd daemon
systemctl --user daemon-reload

echo "✓ Workout locker service and timer removed"
