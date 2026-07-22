/// Dialog shown after a workout is finished, summarising results.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/sync_service.dart';
import 'package:workout_app/ui/theme.dart';

/// Dialog that summarises a completed workout and reports the sync status.
class WorkoutSummaryDialog extends StatelessWidget {
  /// Creates a [WorkoutSummaryDialog].
  const WorkoutSummaryDialog({
    required this.session,
    required this.syncResult,
    super.key,
  });

  /// The completed workout session to summarise.
  final WorkoutSession session;

  /// Result of writing the session to disk/HTTP server.
  final SyncResult syncResult;

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '${d.inHours > 0 ? '${d.inHours}h ' : ''}${m}m ${s}s';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final succeeded = session.fullySucceeded;
    return AlertDialog(
      backgroundColor: colorScheme.surfaceContainerHigh,
      title: Text(
        succeeded ? 'Workout Complete! 💪' : 'Workout Done',
        style: TextStyle(
          color: succeeded ? status.success : status.warning,
          fontWeight: FontWeight.bold,
        ),
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Duration: ${_fmt(session.duration)}',
            style: TextStyle(color: colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 8),
          ...session.exercises.map(
            (e) => Text(
              '${e.exercise.name}: ${e.succeeded ? "✓" : "✗"}',
              style: TextStyle(
                color: e.succeeded ? status.success : colorScheme.error,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            syncResult.success
                ? 'Saved to ${syncResult.path}'
                : 'Sync failed: ${syncResult.error}',
            style: TextStyle(
              color: syncResult.success
                  ? colorScheme.onSurfaceVariant
                  : colorScheme.error,
              fontSize: AppTextSize.caption,
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.of(context).popUntil((r) => r.isFirst);
          },
          child: Text(
            'Back to Home',
            style: TextStyle(color: colorScheme.primary),
          ),
        ),
      ],
    );
  }
}
