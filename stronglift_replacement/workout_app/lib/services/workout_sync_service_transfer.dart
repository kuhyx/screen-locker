// Manual-workout records for the user-owned export/import.
//
// An `extension` in a `part` -- see storage_service_backup.dart for why.
part of 'workout_sync_service.dart';

/// Reads and writes the manual-workout slice of the shared crdt_sync log.
extension WorkoutSyncServiceTransfer on WorkoutSyncService {
  /// Every manual-workout record on every device log, tombstones included,
  /// merged with [mergeLogs]; null when the remote cannot be read.
  ///
  /// Unlike [readMergedManualPayloads] this keeps the records (HLCs and
  /// deletions) so they can be carried across and merged back losslessly, and
  /// it tells "empty" (`{}`) from "unreachable" (null) -- an export must not
  /// claim there are no manual workouts when it merely could not look.
  Future<Log?> readManualLog() async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      debugPrint('WorkoutSyncService: manual log NOT read -- sync not set up.');
      return null;
    }
    final github = GitHubClient(
      owner: owner,
      repo: repo,
      token: settings.token,
      httpClient: _httpClient,
    );
    final firebase = await _openFirebase();
    final client = firebase == null
        ? github
        : MirrorStore(primary: firebase, mirror: github);
    try {
      var merged = <String, Record>{};
      for (final device in await client.listDirectory(_pathPrefix)) {
        final text = await client.getFileText(
          '$_pathPrefix/$device/$_logFilename',
        );
        if (text != null) merged = mergeLogs(merged, _decode(text));
      }
      return {
        for (final e in merged.entries)
          if (_isManual(e.value)) e.key: e.value,
      };
    } on Object catch (error, stackTrace) {
      log(
        'WorkoutSyncService.readManualLog failed',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    } finally {
      github.close();
      firebase?.close();
    }
  }

  /// Merges [records] into this device's log and syncs, in one round trip.
  ///
  /// Same never-throw, always-report contract as [pushManual].
  Future<PushResult> pushManualLog(Log records) async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      const reason = 'sync not configured (no Firebase account, no token)';
      log('WorkoutSyncService.pushManualLog skipped: $reason', level: 900);
      return const PushResult(pushed: false, reason: reason);
    }
    return await _session(settings.token).run(
      operation: 'pushManualLog',
      successReason: 'pushed',
      failurePrefix: 'push failed',
      additions: records,
    );
  }

  /// A manual workout, or the tombstone of one: tombstones carry no payload,
  /// so the id (`manual:<date>T<HH:MM>`) is what identifies them.
  static bool _isManual(Record r) {
    if (r.id.startsWith('manual:')) return true;
    final payload = r.fields['payload']?.$1;
    return payload is Map && payload['kind'] == kManualWorkoutSyncKind;
  }
}
