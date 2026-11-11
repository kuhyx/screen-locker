/// Dialog shown after a workout is finished, summarising results.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/pc_poke_result.dart';
import 'package:workout_app/services/sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/pc_poke_line.dart';

/// Dialog that summarises a completed workout and reports the sync status.
class WorkoutSummaryDialog extends StatelessWidget {
  /// Creates a [WorkoutSummaryDialog].
  const WorkoutSummaryDialog({
    required this.session,
    required this.syncResult,
    this.pcPoke,
    super.key,
  });

  /// The completed workout session to summarise.
  final WorkoutSession session;

  /// Result of writing the session to disk/HTTP server.
  final SyncResult syncResult;

  /// The direct phone->PC poke started at finish, shown as one status line;
  /// null where none was sent.
  final Future<PokeResult>? pcPoke;

  /// `45:30` or `1:05:00` (textgate: was "Duration: 45m 30s").
  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return d.inHours > 0 ? '${d.inHours}:$m:$s' : '$m:$s';
  }

  String get _saveSemanticsLabel => syncResult.success
      ? 'Saved to ${syncResult.path}' // semantics only
      : 'Sync failed: ${syncResult.error}'; // semantics only

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final succeeded = session.fullySucceeded;
    return AlertDialog(
      backgroundColor: colorScheme.surfaceContainerHigh,
      // textgate: was "Workout Complete! 💪" / "Workout Done".
      title: Icon(
        succeeded ? Icons.emoji_events : Icons.flag,
        size: 40,
        color: succeeded ? status.success : status.warning,
        semanticLabel: succeeded ? 'Workout Complete!' : 'Workout Done',
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.timer,
                size: 18,
                color: colorScheme.onSurfaceVariant,
                semanticLabel: 'Duration',
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                _fmt(session.duration),
                style: TextStyle(color: colorScheme.onSurfaceVariant),
              ),
            ],
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
          // textgate: was "Saved to <path>" / "Sync failed: <error>".
          Icon(
            syncResult.success ? Icons.save : Icons.error_outline,
            key: const Key('summary_save_state'),
            size: 18,
            color: syncResult.success
                ? colorScheme.onSurfaceVariant
                : colorScheme.error,
            semanticLabel: _saveSemanticsLabel,
          ),
          if (pcPoke != null) ...[
            const SizedBox(height: AppSpacing.sm),
            PcPokeLine(poke: pcPoke!),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.of(context).popUntil((r) => r.isFirst);
          },
          child: Icon(
            Icons.home,
            color: colorScheme.primary,
            semanticLabel: 'Back to Home',
          ),
        ),
      ],
    );
  }
}
