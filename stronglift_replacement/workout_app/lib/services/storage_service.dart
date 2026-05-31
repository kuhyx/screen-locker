/// Persistent storage for exercise progression state using SQLite.
library;

import 'dart:convert';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';

/// Per-exercise progression state stored in SQLite.
class ExerciseState {
  ExerciseState({
    required this.name,
    required this.weight,
    required this.reps,
    required this.successStreak,
    required this.failStreak,
    required this.maxWeight,
    required this.successThreshold,
    required this.failThreshold,
  });

  final String name;
  double weight;
  int reps;
  int successStreak;
  int failStreak;
  final double maxWeight;
  int successThreshold;
  int failThreshold;
}

class StorageService {
  StorageService._();
  static StorageService? _instance;
  static StorageService get instance => _instance!;

  late Database _db;

  static Future<StorageService> init() async {
    if (_instance != null) return _instance!;
    final svc = StorageService._();
    await svc._open();
    _instance = svc;
    return svc;
  }

  Future<void> _open() async {
    final dbPath = p.join(await getDatabasesPath(), 'workout_app.db');
    _db = await openDatabase(
      dbPath,
      version: 3,
      onCreate: _createSchema,
      onUpgrade: _migrateSchema,
    );
    await _seedDefaultsIfNeeded();
  }

  Future<void> _createSchema(Database db, int version) async {
    await db.execute('''
      CREATE TABLE exercise_state (
        name TEXT PRIMARY KEY,
        weight REAL NOT NULL,
        reps INTEGER NOT NULL,
        success_streak INTEGER NOT NULL DEFAULT 0,
        fail_streak INTEGER NOT NULL DEFAULT 0,
        max_weight REAL NOT NULL,
        success_threshold INTEGER NOT NULL DEFAULT 3,
        fail_threshold INTEGER NOT NULL DEFAULT 2
      )
    ''');
    await db.execute('''
      CREATE TABLE workout_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        workout_type TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL,
        succeeded INTEGER NOT NULL,
        json TEXT NOT NULL
      )
    ''');
    await db.execute('''
      CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      )
    ''');
    await db.execute('''
      CREATE TABLE active_session (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        json TEXT NOT NULL
      )
    ''');
  }

  Future<void> _migrateSchema(
    Database db,
    int oldVersion,
    int newVersion,
  ) async {
    if (oldVersion < 2) {
      await db.execute(
        'ALTER TABLE exercise_state ADD COLUMN success_threshold INTEGER NOT NULL DEFAULT 3',
      );
      await db.execute(
        'ALTER TABLE exercise_state ADD COLUMN fail_threshold INTEGER NOT NULL DEFAULT 2',
      );
    }
    if (oldVersion < 3) {
      await db.execute(
        'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
      );
      await db.execute(
        'CREATE TABLE IF NOT EXISTS active_session '
        '(id INTEGER PRIMARY KEY CHECK (id = 1), json TEXT NOT NULL)',
      );
    }
  }

  Future<void> _seedDefaultsIfNeeded() async {
    for (final ex in [...workoutA, ...workoutB]) {
      final rows = await _db.query(
        'exercise_state',
        where: 'name = ?',
        whereArgs: [ex.name],
      );
      if (rows.isEmpty) {
        await _db.insert('exercise_state', {
          'name': ex.name,
          'weight': ex.weight,
          'reps': ex.reps,
          'success_streak': 0,
          'fail_streak': 0,
          'max_weight': ex.maxWeight,
          'success_threshold': 3,
          'fail_threshold': 2,
        });
      }
    }
  }

  // ── Settings ───────────────────────────────────────────────────────────────

  Future<String?> _getSetting(String key) async {
    final rows = await _db.query(
      'settings',
      where: 'key = ?',
      whereArgs: [key],
    );
    return rows.isEmpty ? null : rows.first['value'] as String;
  }

  Future<void> _setSetting(String key, String value) async {
    await _db.insert(
      'settings',
      {'key': key, 'value': value},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<String> getNextWorkoutType() async {
    final last = await _getSetting('last_workout_type');
    return last == 'A' ? 'B' : 'A';
  }

  Future<void> setLastWorkoutType(String type) async {
    await _setSetting('last_workout_type', type);
  }

  // ── Active session (crash / exit recovery) ─────────────────────────────────

  Future<void> saveActiveSession(Map<String, dynamic> data) async {
    await _db.insert(
      'active_session',
      {'id': 1, 'json': jsonEncode(data)},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<Map<String, dynamic>?> loadActiveSession() async {
    final rows = await _db.query('active_session', where: 'id = 1');
    if (rows.isEmpty) return null;
    return jsonDecode(rows.first['json'] as String) as Map<String, dynamic>;
  }

  Future<void> clearActiveSession() async {
    await _db.delete('active_session', where: 'id = 1');
  }

  // ── Exercise state ─────────────────────────────────────────────────────────

  Future<ExerciseState?> getExerciseState(String name) async {
    final rows = await _db.query(
      'exercise_state',
      where: 'name = ?',
      whereArgs: [name],
    );
    if (rows.isEmpty) return null;
    final r = rows.first;
    return ExerciseState(
      name: r['name'] as String,
      weight: r['weight'] as double,
      reps: r['reps'] as int,
      successStreak: r['success_streak'] as int,
      failStreak: r['fail_streak'] as int,
      maxWeight: r['max_weight'] as double,
      successThreshold: r['success_threshold'] as int? ?? 3,
      failThreshold: r['fail_threshold'] as int? ?? 2,
    );
  }

  Future<List<ExerciseState>> getAllExerciseStates() async {
    final allNames = [...workoutA, ...workoutB].map((e) => e.name).toSet();
    final states = <ExerciseState>[];
    for (final name in allNames) {
      final s = await getExerciseState(name);
      if (s != null) states.add(s);
    }
    return states;
  }

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

  Future<void> setExerciseWeight(String name, double weight) async {
    await _db.update(
      'exercise_state',
      {'weight': weight, 'success_streak': 0, 'fail_streak': 0},
      where: 'name = ?',
      whereArgs: [name],
    );
  }

  Future<List<Exercise>> getCurrentExercises(String workoutType) async {
    final template = workoutType == 'A' ? workoutA : workoutB;
    final result = <Exercise>[];
    for (final ex in template) {
      final state = await getExerciseState(ex.name);
      if (state == null) {
        result.add(ex);
      } else {
        result.add(ex.copyWith(weight: state.weight, reps: state.reps));
      }
    }
    return result;
  }

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
        final newWeight =
            (state.weight - kWeightIncrement).clamp(0.0, state.maxWeight);
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
        double newWeight = state.weight;
        int newReps = state.reps;

        if (shouldProgress) {
          if (state.weight >= state.maxWeight) {
            newReps = state.reps + 1;
          } else {
            newWeight =
                (state.weight + kWeightIncrement).clamp(0.0, state.maxWeight);
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
  }

  Future<DateTime?> getLastWorkoutDate() async {
    final rows = await _db.rawQuery(
      'SELECT date FROM workout_history ORDER BY date DESC LIMIT 1',
    );
    if (rows.isEmpty) return null;
    return DateTime.tryParse(rows.first['date'] as String);
  }

  Future<List<Map<String, dynamic>>> getWorkoutHistory({
    int limit = 60,
  }) async {
    return _db.rawQuery(
      'SELECT date, workout_type, duration_seconds, succeeded, json '
      'FROM workout_history ORDER BY date DESC LIMIT ?',
      [limit],
    );
  }
}
