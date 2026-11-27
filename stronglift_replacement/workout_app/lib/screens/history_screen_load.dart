// Loading the history: local rows and the cached synced log first, then the
// live read in the background.
//
// A `part` so the extension keeps reaching the private `_HistoryScreenState`
// fields; it mutates them through the `_applyState` shim because `setState`
// is `@protected` and cannot be called from an extension.
part of 'history_screen.dart';

/// Offline-first loading for the history screen.
extension _HistoryLoad on _HistoryScreenState {
  /// Shows what this phone already has, then refreshes from the backends.
  ///
  /// The spinner only covers the local reads. The live read used to come
  /// first, so an offline or slow network hid even this phone's own sessions
  /// behind it.
  Future<void> _load() async {
    final sync = _syncService();
    await _show(await sync.readCachedWorkoutPayloads());
    final remote = await sync.readMergedWorkoutPayloads();
    // Put any of this device's own sessions that only exist remotely back into
    // the local table. A reinstall wipes local history while Firebase/GitHub
    // keep it; without this the app silently shows less history than actually
    // happened. Only from the live read: the cache holds this phone's own
    // pushes, so restoring from it would undo a local delete.
    await StorageService.instance.restoreSyncedSessions(remote);
    // The live read was merged into the cache, which now holds both.
    await _show(await sync.readCachedWorkoutPayloads());
  }

  /// Puts the local history plus [payloads] (synced records) on screen.
  Future<void> _show(List<Map<String, dynamic>> payloads) async {
    final rows = await StorageService.instance.getWorkoutHistory(limit: 200);
    final names = <String>[];
    final seen = <String>{};
    for (final row in rows) {
      final json = jsonDecode(row['json'] as String) as Map<String, dynamic>;
      for (final ex in (json['exercises'] as List? ?? const [])) {
        final name = (ex as Map<String, dynamic>)['name'] as String;
        if (seen.add(name)) names.add(name);
      }
    }
    final today = dayKey((widget.clock ?? DateTime.now)());
    final runs = await StorageService.instance.listRuns();
    // The phone's own copy of a run (it has the map) replaces the PC's entry.
    final synced = withoutLocalRuns(_syncedOnly(payloads, today), runs);
    final planned = _plannedOnly(payloads, today);
    if (!mounted) return;
    _applyState(() {
      _rows = rows;
      _syncedRows = synced;
      _plannedRows = planned;
      _runs = runs;
      _exerciseNames = names;
      _loading = false;
    });
  }
}
