#!/bin/bash
# Script to remove screen locker from i3 autostart

I3_CONFIG="$HOME/.config/i3/config"

# Check if i3 config exists
if [ ! -f "$I3_CONFIG" ]; then
    echo "Error: i3 config not found at $I3_CONFIG"
    exit 1
fi

# Check if autostart line exists
if ! grep -q "exec.*screen_lock.py" "$I3_CONFIG"; then
    echo "Screen locker autostart not found in i3 config"
    exit 0
fi

# Show what will be removed
echo "Found screen locker configuration:"
grep -B1 "exec.*screen_lock.py" "$I3_CONFIG"
echo ""

read -p "Remove screen locker from autostart? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Remove the autostart lines
    sed -i '/# Workout screen locker on startup/d' "$I3_CONFIG"
    sed -i '/exec.*screen_lock\.py/d' "$I3_CONFIG"
    echo "✓ Screen locker removed from i3 autostart"
    echo "Changes will take effect on next i3 restart"
else
    echo "Cancelled"
fi
