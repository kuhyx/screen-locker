// Reading and merging payloads back out of the sync backends.
//
// An `extension` in a `part` -- see storage_service_backup.dart for why.
part of 'workout_sync_service.dart';

/// Reads merged workout/manual payloads across every device log.
extension WorkoutSyncServiceRead on WorkoutSyncService {


  Future<List<Map<String, dynamic>>> _readMergedPayloads({String? kind}) async {
    final settings = await SyncSettings.load();
    if (!settings.isConfigured && !await _hasFirebaseAccount()) {
      debugPrint(
        'WorkoutSyncService: NOT reading synced workouts — no sync backend '
        'configured in Settings, so this phone cannot see the PC history.',
      );
      return const [];
    }

    try {
      return await _fetchPayloads(settings.token, kind);
    } on GitHubSyncError catch (error) {
      var failure = error;
      // A stale keystore token shadows a good backup (SyncSettings.load only
      // falls back when the keystore is EMPTY), so retry once from the backup
      // rather than leaving history silently incomplete.
      final recovered = await SyncSettings.recoverFromBackup(settings.token);
      if (recovered != null) {
        try {
          final payloads = await _fetchPayloads(recovered, kind);
          debugPrint(
            'WorkoutSyncService: recovered the sync token from backup after '
            'the stored one was rejected ($failure).',
          );
          return payloads;
        } on GitHubSyncError catch (retryError) {
          failure = retryError;
        }
      }
      final which = kind ?? 'any';
      debugPrint(
        'WorkoutSyncService: FAILED reading synced workouts '
        '(kind=$which) from $owner/$repo: $failure — history may be incomplete.',
      );
      return const [];
    }
  }

  Future<List<Map<String, dynamic>>> _fetchPayloads(
    String token,
    String? kind,
  ) async {
    final github = GitHubClient(
      owner: owner,
      repo: repo,
      token: token,
      httpClient: _httpClient,
    );
    // Read-only: MirrorStore reads the union of both, so a workout logged
    // against either backend still shows up during the cutover.
    final firebase = await _openFirebase();
    final client = firebase == null
        ? github
        : MirrorStore(primary: firebase, mirror: github);
    try {
      final merged = <String, Record>{};
      final tombstoned = <String>{};
      for (final device in await client.listDirectory(_pathPrefix)) {
        final text = await client.getFileText(
          '$_pathPrefix/$device/$_logFilename',
        );
        if (text == null) continue;
        final log = _decode(text);
        _collectTombstones(log, tombstoned);
        _mergeRecords(log, merged, kind: kind);
      }
      // Suppression is applied across the whole device union, never per file:
      // one device tombstoning a record while another still holds it live must
      // delete it, and a per-file skip would just let the live copy win the
      // merge. Mirrors the PC's `_tombstoned_ids` (screen_locker/_sync_records.py).
      tombstoned.forEach(merged.remove);
      return merged.values
          .map((r) => (r.fields['payload']!.$1! as Map).cast<String, dynamic>())
          .toList();
    } finally {
      github.close();
      firebase?.close();
    }
  }

  /// Collects the ids this device log marks deleted, into [into].
  ///
  /// Gathered before the kind filter runs, because a tombstone carries no
  /// payload to match on: filtering first would drop the deletion and let the
  /// live copy from another device survive the merge.
  static void _collectTombstones(Log log, Set<String> into) {
    for (final entry in log.entries) {
      if (entry.value.deleted) into.add(entry.key);
    }
  }

  /// Merges records into [into], keeping the highest-HLC copy of each id.
  ///
  /// [kind] filters on the payload's `kind` discriminator; pass null to keep
  /// every workout kind. The manual-workout budget must only ever see manual
  /// self-reports (a verified run must not consume that budget), while the
  /// history view wants everything — hence the filter rather than two merges.
  static void _mergeRecords(Log log, Map<String, Record> into, {String? kind}) {
    for (final entry in log.entries) {
      final field = entry.value.fields['payload'];
      if (field == null) continue;
      final payload = field.$1;
      if (payload is! Map) continue;
      if (kind != null && payload['kind'] != kind) continue;
      final existing = into[entry.key];
      if (existing == null || existing.fields['payload']!.$2 < field.$2) {
        into[entry.key] = entry.value;
      }
    }
  }

}
