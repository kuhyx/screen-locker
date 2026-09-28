/// A one-line "sync is not set up" strip for the top of the workout screen.
///
/// The home screen's `SyncStatusCard` used to be the only place this was
/// said, and it deliberately sat *before* the workout. Now that a launch
/// can jump straight into the workout, the warning has to travel with it or
/// a workout gets logged into a void again.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/ui/theme.dart';

/// Tells the user this workout will not reach the PC until sync is set up.
class SyncSetupBanner extends StatelessWidget {
  /// Creates the banner.
  const SyncSetupBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      child: Row(
        children: [
          Icon(Icons.cloud_off, size: 16, color: colorScheme.error),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'Sync not set up — this workout will NOT count. '
              'Set it up in Settings.',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colorScheme.error),
            ),
          ),
        ],
      ),
    );
  }
}
