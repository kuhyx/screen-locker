/// The home screen's sync-status card.
///
/// Sits above the workout card so a disconnected phone says so *before* the
/// workout, not after. A workout was once logged into a void because the app
/// stayed silent about being disconnected; the three unhealthy states here
/// all offer the fix rather than just reporting the problem.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/services/sync_status.dart';
import 'package:workout_app/ui/theme.dart';

/// Renders a [SyncStatus] as a card, with an action for the unhealthy states.
class SyncStatusCard extends StatelessWidget {
  /// Creates the card.
  const SyncStatusCard({
    required this.status,
    required this.onRetry,
    required this.onSetUp,
    super.key,
  });

  /// What to show.
  final SyncStatus status;

  /// Runs another sync tick ([SyncState.failed] / [SyncState.outOfDate]).
  final VoidCallback onRetry;

  /// Opens sync settings ([SyncState.notConnected]).
  final VoidCallback onSetUp;

  /// Renders a duration as a number plus a one-letter unit: `5m`, `3h`,
  /// `2d`. Under a minute is `0m` (textgate: was "just now" / "5m ago").
  static String describeAge(Duration age) {
    if (age.inMinutes < 60) return '${age.inMinutes}m';
    if (age.inHours < 24) return '${age.inHours}h';
    return '${age.inDays}d';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final statusColors = Theme.of(context).extension<AppStatusColors>()!;

    // The healthy state is a compact one-liner on purpose: a full card that
    // is always there becomes wallpaper, and then the unhealthy ones stop
    // being noticed too. textgate: was "Synced 5m ago"; now glyph + age.
    if (status.state == SyncState.synced) {
      final age = status.age;
      return Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.cloud_done,
            size: 16,
            color: statusColors.success,
            semanticLabel: 'Synced',
          ),
          if (age != null) ...[
            const SizedBox(width: 8),
            Text(
              describeAge(age),
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: statusColors.success),
            ),
          ],
        ],
      );
    }

    // SyncState.synced returned above, so only the three unhealthy states
    // reach here. `notConnected` is the default arm rather than a listed one
    // so the switch has no unreachable branch to leave uncovered.
    // textgate: the old title / body / button words are spoken only now;
    // the painted card is state glyph + age + action glyph, accent-bordered.
    final (
      icon,
      accent,
      spoken,
      actionIcon,
      actionSpoken,
      action,
    ) = switch (status.state) {
      SyncState.failed => (
        Icons.sync_problem,
        colorScheme.error,
        'Sync failed. ${status.reason ?? 'The last attempt failed.'}',
        Icons.refresh,
        'Retry',
        onRetry,
      ),
      SyncState.outOfDate => (
        Icons.cloud_queue,
        statusColors.warning,
        status.age == null
            ? 'Sync out of date. Never synced successfully.'
            : 'Sync out of date. Last synced ${describeAge(status.age!)} ago.',
        Icons.refresh,
        'Retry',
        onRetry,
      ),
      // notConnected (and, unreachably, synced) land here.
      _ => (
        Icons.cloud_off,
        colorScheme.error,
        'Not connected to sync. '
            'This workout will NOT count until sync is set up.',
        // Not the gear: the home app bar already uses it for Settings.
        Icons.add_link,
        'Set up sync',
        onSetUp,
      ),
    };
    final age = status.age;

    return Card(
      color: colorScheme.surfaceContainerHigh,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: accent),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon, color: accent, semanticLabel: spoken),
            if (status.state == SyncState.outOfDate && age != null) ...[
              const SizedBox(width: 12),
              Text(
                describeAge(age),
                style: Theme.of(
                  context,
                ).textTheme.titleSmall?.copyWith(color: accent),
              ),
            ],
            const Spacer(),
            IconButton(
              onPressed: action,
              color: accent,
              icon: Icon(actionIcon, semanticLabel: actionSpoken),
            ),
          ],
        ),
      ),
    );
  }
}
