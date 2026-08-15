// Backup, restore, and the sync marker settings.
//
// An `extension` in a `part` rather than a separate library: Dart cannot
// continue a class body across files, but library-private members (`_db`,
// `_getSetting`) are still reachable from a part, so these methods keep
// working unchanged and callers still say `StorageService.instance.foo()`.
part of 'storage_service.dart';

/// Backup/restore and the last-synced markers.
extension StorageServiceBackup on StorageService {
  /// Exports all persistent data to external storage as a JSON snapshot.
  ///
  /// Refuses to overwrite a richer existing backup with a freshly-seeded,
  /// history-less DB. That combination is never a real state worth saving: it
  /// only happens when a restore failed (permission denied, unreadable file)
  /// and the DB is sitting at [workoutA]/[workoutB] defaults. The old code
  /// exported anyway on the first write after such a seed, replacing the only
  /// off-device copy of months of progression with default rows — the step
  /// that turned the 2026-08-05 reinstall from recoverable into permanent.
  Future<void> _backupNow() async {
    final exerciseRows = await _db.query('exercise_state');
    final historyRows = await _db.query('workout_history');
    final settingsRows = await _db.query('settings');

    if (historyRows.isEmpty) {
      final existing = await BackupService.instance.readBackup();
      final existingHistory =
          (existing?['workout_history'] as List?) ?? const [];
      if (existingHistory.isNotEmpty) {
        debugPrint(
          'WorkoutApp: REFUSING to overwrite the backup — this DB has no '
          'workout history but the backup holds ${existingHistory.length} '
          'session(s). A restore almost certainly failed; keeping the backup '
          'so the data stays recoverable.',
        );
        return;
      }
    }

    await BackupService.instance.export({
      'exercise_state': exerciseRows,
      'workout_history': historyRows,
      'settings': settingsRows,
    });
  }

  /// Whether this database has never recorded a workout on this install.
  ///
  /// "Empty" means no workout history and no [last_workout_type] setting —
  /// the state a fresh install or a `pm clear` leaves behind, and the only
  /// state in which overwriting local rows wholesale is safe.
  ///
  /// Shared with the Firebase progression restore so both restore paths agree
  /// on what "fresh install" means. Deliberately NOT a per-exercise value
  /// comparison: [resetExerciseToDefaults] leaves `reps` and `max_weight`
  /// alone, so resetting an exercise that already sits at its default reps
  /// produces a row byte-identical to a seeded one. Treating that as "fresh"
  /// would let a pull silently revert a reset the user just performed.
  Future<bool> looksFreshlyInstalled() async {
    final hasHistory =
        (await _db.rawQuery('SELECT COUNT(*) AS c FROM workout_history'))
            .first['c'] as int? ??
        0;
    if (hasHistory > 0) return false;
    return await _getSetting('last_workout_type') == null;
  }

  /// Whether this install has reconciled its progression with Firebase.
  ///
  /// This — NOT [looksFreshlyInstalled] — is what gates pushing progression
  /// up. The freshness test is unusable there because the only production
  /// caller (`_finishWorkout`) writes a `workout_history` row and
  /// `last_workout_type` *before* it pushes, so the DB has stopped looking
  /// fresh by the time the guard runs: the guard could never fire, and a
  /// reinstall that connected Firebase late would overwrite every real remote
  /// record with factory defaults on its first finished workout.
  ///
  /// It is also wrong for hand edits: `setExerciseWeight` and
  /// `resetExerciseToDefaults` write neither history nor `last_workout_type`,
  /// so a DB still "looks fresh" after them and the next pull would revert the
  /// user's own change.
  Future<bool> hasSyncedProgression() async =>
      await _getSetting(_progressionSyncedKey) != null;

  /// Records that remote progression has been reconciled, so later pushes are
  /// allowed and later pulls stop overwriting local state.
  Future<void> markProgressionSynced() =>
      _setSetting(_progressionSyncedKey, DateTime.now().toIso8601String());

  static const _progressionSyncedKey = 'progression_synced_at';

  /// When a workout sync last SUCCEEDED, or null if one never has.
  ///
  /// Drives the home screen's "Out of date" card. Nothing persisted a
  /// last-sync time before — which is why the app could sit disconnected for
  /// days with nothing on screen saying so.
  Future<DateTime?> getLastSyncedAt() async {
    final raw = await _getSetting(_lastSyncedAtKey);
    if (raw == null) return null;
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) {
      // Never silently treat a corrupt timestamp as "never synced": that
      // would show the nag card forever with no clue why.
      debugPrint(
        'WorkoutApp: last_synced_at is not a valid timestamp ($raw) — '
        'treating this device as never synced until the next success.',
      );
      return null;
    }
    return parsed;
  }

  /// Records that a sync just succeeded.
  Future<void> markSyncedNow([DateTime? at]) => _setSetting(
    _lastSyncedAtKey,
    (at ?? DateTime.now()).toIso8601String(),
  );

  static const _lastSyncedAtKey = 'last_synced_at';

  /// Restores from backup if the local DB is empty (fresh install).
  ///
  /// "Empty" means no workout history and no [last_workout_type] setting.
  Future<void> restoreFromBackupIfNeeded() async {
    if (!await looksFreshlyInstalled()) return; // DB has real data

    final backup = await BackupService.instance.readBackup();
    if (backup == null) {
      // readBackup() has already said which case this is. Say what it MEANS:
      // the DB is sitting at seeded defaults and that is now the live state.
      debugPrint(
        'WorkoutApp: no backup restored — the database is at factory defaults. '
        'If this is a reinstall, progression state (weights, reps, streaks) '
        'has been lost and must be re-entered.',
      );
      return;
    }

    await _db.transaction((txn) async {
      for (final row in (backup['exercise_state'] as List? ?? [])
          .cast<Map<String, dynamic>>()) {
        await txn.insert(
          'exercise_state',
          row,
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      for (final row in (backup['workout_history'] as List? ?? [])
          .cast<Map<String, dynamic>>()) {
        await txn.insert(
          'workout_history',
          row,
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      for (final row in (backup['settings'] as List? ?? [])
          .cast<Map<String, dynamic>>()) {
        await txn.insert(
          'settings',
          row,
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
    });
  }
}
