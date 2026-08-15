// Progression application and session recording.
//
// Split from storage_service_exercises.dart: that file reads and writes a
// single exercise's row, this one advances progression and records whole
// sessions. See storage_service_backup.dart for why these are `part`
// extensions.
part of 'storage_service.dart';

/// Progression application and session recording.
extension StorageServiceSessions on StorageService {
  /// Applies progressive overload or regression based on [succeededExercises].
  Future<void> applyProgression({
    required Map<String, bool> succeededExercises,
    required DateTime lastWorkoutDate,
  }) async {
    final daysSince = DateTime.now().difference(lastWorkoutDate).inDays;
    final hadBreak = daysSince > 7;

    for (final entry in succeededExercises.entries) {
      final state = await getExerciseState(entry.key);
      if (state == null) continue;

      if (hadBreak) {
        final newWeight = (state.weight - kWeightIncrement).clamp(
          0.0,
          state.maxWeight,
        );
        await _db.update(
          'exercise_state',
          {'weight': newWeight, 'success_streak': 0, 'fail_streak': 0},
          where: 'name = ?',
          whereArgs: [entry.key],
        );
        continue;
      }

      if (entry.value) {
        final newStreak = state.successStreak + 1;
        final shouldProgress = newStreak >= state.successThreshold;
        var newWeight = state.weight;
        var newReps = state.reps;

        if (shouldProgress) {
          if (state.weight >= state.maxWeight) {
            newReps = state.reps + 1;
          } else {
            newWeight = (state.weight + kWeightIncrement).clamp(
              0.0,
              state.maxWeight,
            );
          }
        }

        await _db.update(
          'exercise_state',
          {
            'weight': newWeight,
            'reps': newReps,
            'success_streak': shouldProgress ? 0 : newStreak,
            'fail_streak': 0,
          },
          where: 'name = ?',
          whereArgs: [entry.key],
        );
      } else {
        final newStreak = state.failStreak + 1;
        final shouldRegress = newStreak >= state.failThreshold;
        final newWeight = shouldRegress
            ? (state.weight - kWeightIncrement).clamp(0.0, state.maxWeight)
            : state.weight;

        await _db.update(
          'exercise_state',
          {
            'weight': newWeight,
            'fail_streak': shouldRegress ? 0 : newStreak,
            'success_streak': 0,
          },
          where: 'name = ?',
          whereArgs: [entry.key],
        );
      }
    }
  }

  /// Persists a completed session to the workout history table.
  Future<void> saveSession({
    required String date,
    required String workoutType,
    required int durationSeconds,
    required bool succeeded,
    required String json,
  }) async {
    await _db.insert('workout_history', {
      'date': date,
      'workout_type': workoutType,
      'duration_seconds': durationSeconds,
      'succeeded': succeeded ? 1 : 0,
      'json': json,
    });
    unawaited(_backupNow());
  }

  /// Returns the date of the most recent completed session, or null.
  Future<DateTime?> getLastWorkoutDate() async {
    final rows = await _db.rawQuery(
      'SELECT date FROM workout_history ORDER BY date DESC LIMIT 1',
    );
    if (rows.isEmpty) return null;
    return DateTime.tryParse(rows.first['date']! as String);
  }

  /// Returns up to [limit] rows from workout history, newest first.
  /// Inserts synced sessions this device has no local record of.
  ///
  /// These are the user's OWN completed workouts, already in Firebase/GitHub;
  /// a reinstall wipes the local `workout_history` table while the remote copy
  /// survives, so the app ends up showing far less history than actually
  /// happened. This puts the real records back rather than inventing anything.
  ///
  /// Idempotent: a session is matched on (date, start_time) taken from the
  /// payload, so repeated syncs never duplicate a row. Sessions the device
  /// already has always win -- the local row is the one the progression
  /// engine acted on.
  ///
  /// Returns the number of sessions restored.
  Future<int> restoreSyncedSessions(
    List<Map<String, dynamic>> payloads,
  ) async {
    if (payloads.isEmpty) return 0;
    final existing = await _db.query('workout_history', columns: ['json']);
    final seen = <String>{
      for (final row in existing) _sessionKey(_decodeJson(row['json'])),
    };

    var restored = 0;
    for (final payload in payloads) {
      // Only real sessions: a payload with no exercises is a PC-side
      // runnerup/manual record, which belongs in the synced list, not here.
      if (payload['exercises'] is! List) continue;
      final key = _sessionKey(payload);
      if (key.isEmpty || seen.contains(key)) continue;
      seen.add(key);
      await _db.insert('workout_history', {
        'date': payload['date'] as String? ?? '',
        'workout_type': payload['workout_type'] as String? ?? '',
        'duration_seconds': (payload['duration_seconds'] as num?)?.toInt() ?? 0,
        'succeeded': (payload['succeeded'] as bool? ?? false) ? 1 : 0,
        'json': jsonEncode(payload),
      });
      restored++;
    }
    if (restored > 0) {
      debugPrint('WorkoutApp: restored $restored synced session(s) locally.');
      unawaited(_backupNow());
    }
    return restored;
  }

  /// Identity of a session: its date plus start time, both from the payload.
  ///
  /// `start_time` alone would be enough, but pairing it with the date keeps
  /// the key readable in logs and survives a payload missing either field.
  static String _sessionKey(Map<String, dynamic>? payload) {
    if (payload == null) return '';
    final start = payload['start_time'] as String? ?? '';
    final date = payload['date'] as String? ?? '';
    return start.isEmpty && date.isEmpty ? '' : '$date|$start';
  }

  static Map<String, dynamic>? _decodeJson(Object? raw) {
    if (raw is! String || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      return decoded is Map<String, dynamic> ? decoded : null;
    } on FormatException catch (error) {
      // A corrupt local row must not block restoring the rest; it simply
      // cannot be matched against, so it is treated as "not seen".
      debugPrint(
        'WorkoutApp: a stored session row is not valid JSON ($error) — '
        'treating it as unseen, so a remote copy may be re-imported.',
      );
      return null;
    }
  }
}
