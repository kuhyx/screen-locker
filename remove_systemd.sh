#!/bin/bash
# Remove workout locker systemd service

SERVICE_NAME="workout-locker.service"
TIMER_NAME="workout-locker.timer"
USER_SERVICE_DIR="$HOME/.config/systemd/user"

# Every unit install_systemd.sh creates. Removal has to enumerate all of them,
# or a "removed" locker keeps firing from a timer nobody remembers installing.
UNITS=(
	"$SERVICE_NAME"
	"$TIMER_NAME"
	"early-bird-workout-check.timer"
	"workout-sync.timer"
	"workout-sync.service"
)

for unit in "${UNITS[@]}"; do
	systemctl --user stop "$unit" 2>/dev/null
	systemctl --user disable "$unit" 2>/dev/null
	rm -f "$USER_SERVICE_DIR/$unit"
done

# Reload systemd daemon
systemctl --user daemon-reload

echo "✓ Workout locker services and timers removed"
