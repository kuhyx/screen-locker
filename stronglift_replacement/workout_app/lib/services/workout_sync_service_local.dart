// The local half of sync: the outbox a push writes first, the cache every
// read keeps, and the "is sync set up" gate the ticks share.
//
// An `extension` in a `part` -- see storage_service_backup.dart for why.
part of 'workout_sync_service.dart';

/// Why a tick did nothing: no Firebase account and no GitHub token.
const kSyncNotConfigured =
    'sync not configured (no Firebase account, no token)';

/// Local-first storage around the network ticks.
extension WorkoutSyncServiceLocal on WorkoutSyncService {
  /// Runs [tick] with the GitHub token, or reports that sync is not set up.
  ///
  /// Either backend counts. Gating on the GitHub token alone silently
  /// dropped every push from a device connected only to Firebase.
  Future<PushResult> _whenConfigured(
    String operation,
    Future<PushResult> Function(String token) tick,
  ) async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      log(
        'WorkoutSyncService.$operation skipped: $kSyncNotConfigured',
        level: 900,
      );
      return const PushResult(pushed: false, reason: kSyncNotConfigured);
    }
    return await tick(settings.token);
  }

  /// Writes [record] to the local log, so a failed push loses nothing.
  ///
  /// Never throws: the workout itself is already in the history table, and
  /// the push still goes ahead. A failure here is logged at error level,
  /// since it means a later tick cannot re-send this record.
  Future<void> _keepLocally(Record record) async {
    try {
      await (await _openLogStore()).upsert(record);
    } on Object catch (error, stackTrace) {
      log(
        'WorkoutSyncService: could not keep ${record.id} locally; if this '
        'push fails no later tick re-sends it',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  /// Merges [pulled] into the local log, so it stays readable offline.
  ///
  /// Never throws: the caller already has the live answer; losing the cached
  /// copy only costs the next offline read, and is logged at error level.
  Future<void> _cacheLocally(Log pulled) async {
    try {
      final store = await _openLogStore();
      await store.replaceAll(mergeLogs(store.snapshot(), pulled));
    } on Object catch (error, stackTrace) {
      log(
        'WorkoutSyncService: could not cache the pulled log; offline reads '
        'show the previous copy',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  /// Every workout payload the local log holds: this device's own records
  /// plus everything the last ticks pulled. No network, so it answers at
  /// once and offline; tombstoned records are left out, as in
  /// [readMergedWorkoutPayloads].
  ///
  /// Never throws: an unreadable local log answers empty, logged at error
  /// level, and the live read that follows still fills the view.
  Future<List<Map<String, dynamic>>> readCachedWorkoutPayloads() async {
    try {
      final store = await _openLogStore();
      return [
        for (final record in store.values)
          if (!record.deleted)
            if (record.fields['payload']?.$1 case final Map<dynamic, dynamic> p)
              p.cast<String, dynamic>(),
      ];
    } on Object catch (error, stackTrace) {
      log(
        'WorkoutSyncService: could not read the local log; history waits '
        'for the live read',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return const [];
    }
  }
}
