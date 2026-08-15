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

  /// Renders a duration the way a human would say it.
  static String describeAge(Duration age) {
    if (age.inMinutes < 1) return 'just now';
    if (age.inMinutes < 60) return '${age.inMinutes}m ago';
    if (age.inHours < 24) return '${age.inHours}h ago';
    return '${age.inDays}d ago';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final statusColors = Theme.of(context).extension<AppStatusColors>()!;

    // The healthy state is a compact one-liner on purpose: a full card that
    // is always there becomes wallpaper, and then the unhealthy ones stop
    // being noticed too.
    if (status.state == SyncState.synced) {
      final age = status.age;
      return Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.cloud_done, size: 16, color: statusColors.success),
          const SizedBox(width: 8),
          Text(
            age == null ? 'Synced' : 'Synced ${describeAge(age)}',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: statusColors.success,
            ),
          ),
        ],
      );
    }

    // SyncState.synced returned above, so only the three unhealthy states
    // reach here. `notConnected` is the default arm rather than a listed one
    // so the switch has no unreachable branch to leave uncovered.
    final (icon, accent, title, body, actionLabel, action) = switch (status
        .state) {
      SyncState.failed => (
        Icons.sync_problem,
        colorScheme.error,
        'Sync failed',
        status.reason ?? 'The last sync attempt did not go through.',
        'Retry',
        onRetry,
      ),
      SyncState.outOfDate => (
        Icons.cloud_queue,
        statusColors.warning,
        'Sync out of date',
        status.age == null
            ? 'This device has never synced successfully.'
            : 'Last synced ${describeAge(status.age!)}.',
        'Retry',
        onRetry,
      ),
      // notConnected (and, unreachably, synced) land here.
      _ => (
        Icons.cloud_off,
        colorScheme.error,
        'Not connected to sync',
        'This workout will NOT count until sync is set up.',
        'Set up sync',
        onSetUp,
      ),
    };

    return Card(
      color: colorScheme.surfaceContainerHigh,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: accent),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: accent),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      color: accent,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(body, style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            const SizedBox(width: 8),
            TextButton(onPressed: action, child: Text(actionLabel)),
          ],
        ),
      ),
    );
  }
}
