import 'package:flutter/material.dart';
import 'package:workout_app/services/runnerup_importer.dart';

/// The RunnerUp history import's state as a glyph, never as words: a small
/// spinner while it runs, a warning glyph when it failed (the next start
/// retries), nothing when it is idle or finished.
class RunnerUpImportBadge extends StatelessWidget {
  /// Creates the badge; [status] defaults to the importer's live status.
  const RunnerUpImportBadge({super.key, this.status});

  /// Overrides [runnerUpImportStatus] (tests).
  final ValueNotifier<RunnerUpImportStatus>? status;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<RunnerUpImportStatus>(
      valueListenable: status ?? runnerUpImportStatus,
      builder: (context, state, _) => switch (state) {
        RunnerUpImportStatus.running => const Padding(
          padding: EdgeInsets.all(14),
          child: SizedBox.square(
            dimension: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
        RunnerUpImportStatus.failed => Padding(
          padding: const EdgeInsets.all(14),
          child: Icon(
            Icons.sync_problem,
            color: Theme.of(context).colorScheme.error,
          ),
        ),
        RunnerUpImportStatus.idle ||
        RunnerUpImportStatus.done => const SizedBox.shrink(),
      },
    );
  }
}
