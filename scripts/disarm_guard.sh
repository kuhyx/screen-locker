#!/bin/bash

# ============================================================================
# Disarm guard — shared by arm.sh, install_systemd.sh and install.sh.
#
# Masking the systemd units is not enough on its own. Every install path here
# *copies* unit files into ~/.config/systemd/user, which silently overwrites
# systemd's /dev/null mask symlinks and re-arms enforcement. So a mask alone
# loses to anyone — including a future agent session — running the obvious
# install command by reflex.
#
# The marker file is the deliberate second step: while it exists, no script
# may install units or enable timers. Removing it is an explicit `--rearm`.
#
# Source this file; it defines DISARM_MARKER, report_disarmed,
# refuse_if_disarmed and clear_disarm_marker.
# ============================================================================

# Machine-scoped, deliberately OUTSIDE the repo: a marker inside screen_locker/
# would be erased by `git clean` and is gitignored state anyway. This guards the
# machine, not the checkout.
DISARM_MARKER="${DISARM_MARKER:-$HOME/.local/share/screen_locker/DISARMED}"
readonly DISARM_MARKER

# Print the disarmed banner. Returns 0 when disarmed, 1 when armed.
report_disarmed() {
	[[ -f $DISARM_MARKER ]] || return 1
	echo "================================================================"
	echo "  ENFORCEMENT DISARMED - the screen locker will not trigger."
	echo "================================================================"
	echo "Marker: $DISARM_MARKER"
	if [[ -s $DISARM_MARKER ]]; then
		sed 's/^/  | /' "$DISARM_MARKER"
	fi
	return 0
}

# Hard stop for any path that installs units or enables timers.
# Read-only paths (--status) should call report_disarmed instead.
refuse_if_disarmed() {
	report_disarmed || return 0
	echo "" >&2
	echo "Refusing to arm while disarmed. To re-arm deliberately:" >&2
	echo "    ./arm.sh --rearm" >&2
	exit 1
}

# Remove the marker and unmask the units, so a subsequent install can proceed.
# Masking is what `systemctl --user mask` left behind; `cp` would clobber those
# symlinks silently, so unmask explicitly and let systemd report failures.
clear_disarm_marker() {
	local unit
	local -a masked_units=(
		"workout-locker.service"
		"workout-locker.timer"
		"early-bird-workout-check.timer"
		"workout-sync.service"
		"workout-sync.timer"
	)

	if [[ -f $DISARM_MARKER ]]; then
		rm -f "$DISARM_MARKER"
		echo "Removed disarm marker: $DISARM_MARKER"
	fi

	for unit in "${masked_units[@]}"; do
		# is-enabled prints "masked" for masked units; unmask only those, so a
		# normal re-arm does not spew errors about units that were never masked.
		if [[ $(systemctl --user is-enabled "$unit" 2>/dev/null) == masked* ]]; then
			systemctl --user unmask "$unit"
		fi
	done

	# Restore any unit files that were moved aside when disarming, so `cp` in
	# the caller is not the only thing standing between here and a working unit.
	local stash
	for stash in "$HOME/.config/systemd/user"/disabled-*/; do
		[[ -d $stash ]] || continue
		echo "Note: preserved unit files remain in $stash"
	done

	systemctl --user daemon-reload
}
