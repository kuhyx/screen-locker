// Planned (future-dated) manual workouts: their section and their delete,
// plus the sync service both this and the load use.
//
// A `part` so the extension keeps reaching the private state. Nothing here
// calls `setState`: a delete ends in `_load`, which applies the reload.
part of 'history_screen.dart';

/// The PLANNED section of the history view.
extension _HistoryPlanned on _HistoryScreenState {
  /// The sync service, wired to the test seams this screen was built with.
  WorkoutSyncService _syncService() => WorkoutSyncService(
    httpClient: widget.httpClient,
    firebaseFactory: widget.firebaseFactory,
  );

  /// The planned entries, above everything that already happened; nothing
  /// when there are none.
  List<Widget> _plannedSection() => [
    if (_plannedRows.isNotEmpty) ...[
      const _SectionLabel('PLANNED (not done yet)'),
      const SizedBox(height: 8),
      ..._plannedRows.map(
        (row) => _PlannedWorkoutTile(
          payload: row,
          onDelete: () => _deletePlanned(row),
        ),
      ),
      const SizedBox(height: 16),
    ],
  ];

  /// Deletes the planned manual entry [payload] on every device, after a
  /// confirmation, then re-reads history from sync.
  ///
  /// Re-reading rather than dropping the tile: the tile only goes once the
  /// tombstone is really in the log. A failed push keeps it and says why.
  Future<void> _deletePlanned(Map<String, dynamic> payload) async {
    final date = '${payload['date']}';
    final id = manualSyncRecordId(date, '${payload['start_time']}');
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete planned workout?'),
        content: Text(
          '${payload['source'] ?? 'Manual workout'} on $date at '
          '${payload['start_time']}. It will not be credited.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('KEEP'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('DELETE'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    // Re-checked against the clock: "planned" was decided when History
    // loaded, and a delete confirmed after midnight would cancel a workout
    // that is now today's -- one the PC may already have credited.
    if (!_isPlanned(payload, dayKey((widget.clock ?? DateTime.now)()))) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Not deleted — $date has started, so it is no longer '
            'a planned workout.',
          ),
        ),
      );
      await _load();
      return;
    }
    final result = await _syncService().tombstoneManual(id);
    SandboxLog.event('manual planned delete', {
      'id': id,
      'pushed': result.pushed,
      'reason': result.reason,
    });
    if (!mounted) return;
    if (!result.pushed) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Not deleted — ${result.reason}')));
      return;
    }
    await _load();
  }
}

/// A manual workout dated after today: listed, but not as done.
///
/// The only tile with a delete button. A plan can be cancelled until its day
/// comes; anything that already happened stays history.
class _PlannedWorkoutTile extends StatelessWidget {
  const _PlannedWorkoutTile({required this.payload, required this.onDelete});

  final Map<String, dynamic> payload;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final detail = '${payload['source'] ?? ''}';
    final time = '${payload['start_time'] ?? ''}';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.only(left: 14, top: 4, bottom: 4),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        border: Border.all(color: colorScheme.outline),
      ),
      child: Row(
        children: [
          Icon(Icons.event, color: colorScheme.onSurfaceVariant, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${payload['date']} $time  ·  Planned',
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
          IconButton(
            tooltip: 'Delete planned workout',
            icon: Icon(Icons.delete_outline, color: colorScheme.error),
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }
}
