#!/bin/bash
# Script to add screen locker to i3 autostart
# This will run the workout screen locker on system startup

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SCREEN_LOCK_PATH="$SCRIPT_DIR/screen_lock.py"
I3_CONFIG="$HOME/.config/i3/config"

# Check if screen_lock.py exists
if [ ! -f "$SCREEN_LOCK_PATH" ]; then
    echo "Error: screen_lock.py not found at $SCREEN_LOCK_PATH"
    exit 1
fi

# Make sure screen_lock.py is executable
chmod +x "$SCREEN_LOCK_PATH"

# Check if i3 config exists
if [ ! -f "$I3_CONFIG" ]; then
    echo "Error: i3 config not found at $I3_CONFIG"
    echo "Please create i3 config first or specify correct path"
    exit 1
fi

# Check if autostart line already exists
if grep -q "exec.*screen_lock.py" "$I3_CONFIG"; then
    echo "Screen locker autostart already configured in i3 config"
    echo "Current line:"
    grep "exec.*screen_lock.py" "$I3_CONFIG"
    read -p "Do you want to replace it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Remove old line
        sed -i '/exec.*screen_lock\.py/d' "$I3_CONFIG"
    else
        echo "Keeping existing configuration"
        exit 0
    fi
fi

# Add autostart line to i3 config
echo "" >> "$I3_CONFIG"
echo "# Workout screen locker on startup (production mode)" >> "$I3_CONFIG"
echo "exec --no-startup-id python3 $SCREEN_LOCK_PATH --production" >> "$I3_CONFIG"

echo "✓ Screen locker added to i3 autostart (production mode)"
echo "✓ Configuration added to: $I3_CONFIG"
echo ""
echo "The screen locker will run on next i3 restart/login"
echo ""
echo "To test now, run: i3-msg restart"
echo "To run in demo mode, remove --production flag from $I3_CONFIG"
