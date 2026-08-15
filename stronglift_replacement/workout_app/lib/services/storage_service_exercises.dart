// Per-exercise progression state.
//
// The largest cohesive group: reading and writing exercise_state rows.
// See storage_service_backup.dart for why these are `part` extensions.
part of 'storage_service.dart';

/// Per-exercise progression state.
extension StorageServiceExercises on StorageService {
  // ── Exercise state ─────────────────────────────────────────────────────────

  /// Returns the progression state for [name], or null if not found.
  Future<ExerciseState?> getExerciseState(String name) async {
    final rows = await _db.query(
      'exercise_state',
      where: 'name = ?',
      whereArgs: [name],
    );
    if (rows.isEmpty) return null;
    final r = rows.first;
    return ExerciseState(
      name: r['name']! as String,
      weight: r['weight']! as double,
      reps: r['reps']! as int,
      successStreak: r['success_streak']! as int,
      failStreak: r['fail_streak']! as int,
      maxWeight: r['max_weight']! as double,
      successThreshold: r['success_threshold'] as int? ?? 3,
      failThreshold: r['fail_threshold'] as int? ?? 2,
    );
  }

  /// Returns progression states for every exercise across both plans.
  Future<List<ExerciseState>> getAllExerciseStates() async {
    final allNames = [...workoutA, ...workoutB].map((e) => e.name).toSet();
    final states = <ExerciseState>[];
    for (final name in allNames) {
      final s = await getExerciseState(name);
      if (s != null) states.add(s);
    }
    return states;
  }

  /// Updates the streak thresholds for exercise [name].
  Future<void> setExerciseThresholds(
    String name, {
    required int successThreshold,
    required int failThreshold,
  }) async {
    await _db.update(
      'exercise_state',
      {
        'success_threshold': successThreshold,
        'fail_threshold': failThreshold,
      },
      where: 'name = ?',
      whereArgs: [name],
    );
  }

  /// Sets the target reps for [name], resetting streaks.
  ///
  /// Progression can only ever raise reps (by one, and only once an exercise
  /// is at its max weight), so without this there is no way to lower a rep
  /// target that a defaults re-seed set wrong -- the 2026-08-05 wipe dropped
  /// Situp from 31 to the default 30 with no way back short of editing the DB.
  Future<void> setExerciseReps(String name, int reps) async {
    await _db.update(
      'exercise_state',
      {'reps': reps, 'success_streak': 0, 'fail_streak': 0},
      where: 'name = ?',
      whereArgs: [name],
    );
    unawaited(_backupNow());
  }

  /// Overwrites [state] wholesale, inserting it when the row is absent.
  ///
  /// Used by the Firebase progression restore, which carries a complete record
  /// (weight, reps, both streaks, max weight, both thresholds) and must land it
  /// atomically — a field-by-field update would leave a half-restored row if it
  /// failed partway. Unlike [setExerciseWeight] this deliberately does NOT
  /// reset streaks: the streaks are part of what is being restored.
  ///
  /// Does not trigger a backup write. The caller is restoring INTO a
  /// freshly-seeded database, and `_backupNow()` mid-restore is what previously
  /// let default rows reach the only off-device copy.
  Future<void> replaceExerciseState(ExerciseState state) async {
    await _db.insert('exercise_state', {
      'name': state.name,
      'weight': state.weight,
      'reps': state.reps,
      'success_streak': state.successStreak,
      'fail_streak': state.failStreak,
      'max_weight': state.maxWeight,
      'success_threshold': state.successThreshold,
      'fail_threshold': state.failThreshold,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  /// Sets the working weight for [name], resetting streaks.
  Future<void> setExerciseWeight(String name, double weight) async {
    await _db.update(
      'exercise_state',
      {'weight': weight, 'success_streak': 0, 'fail_streak': 0},
      where: 'name = ?',
      whereArgs: [name],
    );
    unawaited(_backupNow());
  }

  /// Returns exercises for [workoutType] with weights/reps from stored state.
  Future<List<Exercise>> getCurrentExercises(String workoutType) async {
    final template = workoutType == 'A' ? workoutA : workoutB;
    final result = <Exercise>[];
    for (final ex in template) {
      final state = await getExerciseState(ex.name);
      if (state == null) {
        // Defensive: _seedDefaultsIfNeeded guarantees every template exercise
        // has a state row, so this branch is unreachable in practice.
        // coverage:ignore-start
        result.add(ex);
        // coverage:ignore-end
      } else {
        result.add(ex.copyWith(weight: state.weight, reps: state.reps));
      }
    }
    return result;
  }
}
