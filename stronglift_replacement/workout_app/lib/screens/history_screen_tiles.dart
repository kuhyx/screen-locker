// Session list tiles for HistoryScreen.
//
// See history_screen_charts.dart for why these are `part` files.
part of 'history_screen.dart';

class _SyncedWorkoutTile extends StatelessWidget {
  const _SyncedWorkoutTile({required this.payload});

  final Map<String, dynamic> payload;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final kind = '${payload['kind']}';
    final isRun = kind == 'runnerup_verified';
    final label = isRun ? 'Run' : 'Manual';
    final detail = '${payload['source'] ?? ''}';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        // Neutral — this distinguishes entry TYPE (run vs. manual), not a
        // status/judgment, so it doesn't borrow a semantic status color.
        border: Border.all(color: colorScheme.outline),
      ),
      child: Row(
        children: [
          Icon(
            isRun ? Icons.directions_run : Icons.edit_note,
            color: colorScheme.onSurfaceVariant,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${payload['date']}  ·  $label',
                  style: TextStyle(
                    color: colorScheme.onSurface,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                if (detail.isNotEmpty)
                  Text(
                    detail,
                    style: TextStyle(
                      color: colorScheme.onSurfaceVariant,
                      fontSize: AppTextSize.caption,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AllSessionTile extends StatelessWidget {
  const _AllSessionTile({required this.row});

  final Map<String, dynamic> row;

  String _formatDuration(int secs) {
    final h = secs ~/ 3600;
    final m = (secs ~/ 60).remainder(60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return h > 0 ? '${h}h ${m}m ${s}s' : '${m}m ${s}s';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final succeeded = (row['succeeded'] as int) == 1;
    final type = row['workout_type'] as String;
    final date = row['date'] as String;
    final dur = _formatDuration(row['duration_seconds'] as int);
    final statusColor = succeeded ? status.success : colorScheme.error;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        border: Border.all(color: statusColor),
      ),
      child: Row(
        children: [
          Icon(
            succeeded ? Icons.check_circle : Icons.cancel,
            color: statusColor,
            size: 18,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Workout $type  ·  $date',
                  style: TextStyle(
                    color: colorScheme.onSurface,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  dur,
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: AppTextSize.caption,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ExerciseSessionTile extends StatelessWidget {
  const _ExerciseSessionTile({required this.session});

  final Map<String, dynamic> session;

  String _formatDuration(int secs) {
    final h = secs ~/ 3600;
    final m = (secs ~/ 60).remainder(60).toString().padLeft(2, '0');
    final s = (secs % 60).toString().padLeft(2, '0');
    return h > 0 ? '${h}h ${m}m ${s}s' : '${m}m ${s}s';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    final exData = session['exerciseData'] as Map<String, dynamic>;
    final succeeded = (exData['succeeded'] as bool?) == true;
    final date = session['date'] as String;
    final dur = _formatDuration(session['duration_seconds'] as int);
    final weight = (exData['targetWeight'] as num?)?.toDouble();
    final warmupDone = exData['warmupDone'] as bool? ?? false;
    final sets = (exData['sets'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final targetSets = exData['targetSets'] as int? ?? sets.length;
    final doneSets = sets.where((s) => s['succeeded'] == true).length;
    final repsSummary = sets.map((s) => '${s['doneReps']}').join(', ');
    final statusColor = succeeded ? status.success : colorScheme.error;
    final mutedStyle = TextStyle(
      color: colorScheme.onSurfaceVariant,
      fontSize: AppTextSize.caption,
    );

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        border: Border.all(color: statusColor),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(
              succeeded ? Icons.check_circle : Icons.cancel,
              color: statusColor,
              size: 18,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  date,
                  style: TextStyle(
                    color: colorScheme.onSurface,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${weight ?? '?'}kg  ·  $doneSets/$targetSets sets'
                  '  ·  ${warmupDone ? '⬤ warmup' : '○ no warmup'}',
                  style: mutedStyle,
                ),
                if (repsSummary.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text('reps: $repsSummary', style: mutedStyle),
                ],
                const SizedBox(height: 2),
                Text('workout: $dur', style: mutedStyle),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
