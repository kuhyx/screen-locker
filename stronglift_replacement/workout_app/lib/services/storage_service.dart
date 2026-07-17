/// Persistent storage for exercise progression state using SQLite.
library;

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/backup_service.dart';

/// Per-exercise progression state stored in SQLite.
class ExerciseState {
  /// Creates an [ExerciseState] with all required progression fields.
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

  /// Exercise name (matches [Exercise.name], used as primary key).
  final String name;

  /// Current working weight in kg.
  double weight;

  /// Current target reps per set.
  int reps;

  /// Consecutive successful workouts since last progression.
  int successStreak;

  /// Consecutive failed workouts since last regression.
  int failStreak;

  /// Weight cap; reps increase instead of weight when this is reached.
  final double maxWeight;

  /// Successes needed in a row before weight/reps increase.
  int successThreshold;

  /// Failures needed in a row before weight decreases.
  int failThreshold;
}

/// Singleton SQLite service for workout data persistence.
class StorageService {
  StorageService._();
  static StorageService? _instance;

  /// Returns the initialized singleton; throws if [init] was not called first.
  static StorageService get instance => _instance!;

  late Database _db;

  /// Initializes the singleton and opens the database (idempotent).
  static Future<StorageService> init() async {
    if (_instance != null) return _instance!;
    final svc = StorageService._();
    await svc._open();
    _instance = svc;
    return svc;
  }

  // Overrides the DB path for unit tests (set by resetForTesting).
  static String? _testDbPath;

  /// Resets the singleton so [init] can be called again in tests.
  ///
  /// Defaults to an in-memory database so each test starts with a clean
  /// slate and file-based data from other tests does not leak in. Pass a
  /// file [dbPath] to exercise on-disk paths (e.g. schema migrations, which
  /// need a persisted DB opened twice at different versions).
  @visibleForTesting
  static void resetForTesting({String dbPath = ':memory:'}) {
    _instance = null;
    _testDbPath = dbPath;
  }

  Future<void> _open() async {
    final dbPath =
        _testDbPath ??
        // coverage:ignore-start
        p.join(await getDatabasesPath(), 'workout_app.db');
    // coverage:ignore-end
    _db = await openDatabase(
      dbPath,
      version: 3,
      onCreate: _createSchema,
      onUpgrade: _migrateSchema,
      // In tests resetForTesting() reopens a ':memory:' DB per test; sqflite's
      // default singleInstance would hand back the same cached in-memory DB, so
      // data would pile up across tests. Disable it so each test gets a fresh
      // empty DB. Production keeps the default single shared instance.
      singleInstance: _testDbPath == null,
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
        'ALTER TABLE exercise_state '
        'ADD COLUMN success_threshold INTEGER NOT NULL DEFAULT 3',
      );
      await db.execute(
        'ALTER TABLE exercise_state '
        'ADD COLUMN fail_threshold INTEGER NOT NULL DEFAULT 2',
      );
    }
    if (oldVersion < 3) {
      await db.execute(
        'CREATE TABLE IF NOT EXISTS settings '
        '(key TEXT PRIMARY KEY, value TEXT NOT NULL)',
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
    return rows.isEmpty ? null : rows.first['value']! as String;
  }

  Future<void> _setSetting(String key, String value) async {
    await _db.insert(
      'settings',
      {'key': key, 'value': value},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  /// Returns 'A' or 'B' — the type that should be done next.
  Future<String> getNextWorkoutType() async {
    final last = await _getSetting('last_workout_type');
    return last == 'A' ? 'B' : 'A';
  }

  /// Persists [type] as the most recently completed workout type.
  Future<void> setLastWorkoutType(String type) async {
    await _setSetting('last_workout_type', type);
    unawaited(_backupNow());
  }

  // ── Active session (crash / exit recovery) ─────────────────────────────────

  /// Persists [data] as the currently active (in-progress) session.
  ///
  /// Also mirrored to external storage: this table is app-private, so an
  /// uninstall or `pm clear` wipes it and the user loses the set they are
  /// standing on. The mirror survives both.
  Future<void> saveActiveSession(Map<String, dynamic> data) async {
    await _db.insert(
      'active_session',
      {'id': 1, 'json': jsonEncode(data)},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
    unawaited(BackupService.instance.exportActiveSession(data));
  }

  /// Returns the saved active session, or null if none exists.
  ///
  /// Falls back to the external mirror (re-seeding the table from it) when the
  /// table is empty — which is exactly the state right after an app-data wipe,
  /// so the workout resumes on the same set and rep instead of vanishing.
  Future<Map<String, dynamic>?> loadActiveSession() async {
    final rows = await _db.query('active_session', where: 'id = 1');
    if (rows.isNotEmpty) {
      return jsonDecode(rows.first['json']! as String) as Map<String, dynamic>;
    }
    final mirrored = await BackupService.instance.readActiveSession();
    if (mirrored == null) return null;
    await _db.insert(
      'active_session',
      {'id': 1, 'json': jsonEncode(mirrored)},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
    return mirrored;
  }

  /// Removes the active session record (called after a session is committed).
  ///
  /// Clears the external mirror too, so a finished workout cannot be
  /// resurrected by the next [loadActiveSession].
  Future<void> clearActiveSession() async {
    await _db.delete('active_session', where: 'id = 1');
    await BackupService.instance.exportActiveSession(null);
  }

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
  Future<List<Map<String, dynamic>>> getWorkoutHistory({
    int limit = 60,
  }) async {
    return _db.rawQuery(
      'SELECT date, workout_type, duration_seconds, succeeded, json '
      'FROM workout_history ORDER BY date DESC LIMIT ?',
      [limit],
    );
  }

  /// Returns all distinct workout dates (YYYY-MM-DD), newest first.
  Future<List<String>> getAllWorkoutDates() async {
    final rows = await _db.rawQuery(
      'SELECT DISTINCT date FROM workout_history ORDER BY date DESC',
    );
    return rows.map((r) => r['date']! as String).toList();
  }

  /// Resets [name] to its default weight and thresholds, clearing streaks.
  Future<void> resetExerciseToDefaults(String name) async {
    final defaults = [...workoutA, ...workoutB].firstWhere(
      (e) => e.name == name,
      orElse: () => throw Exception('Unknown exercise: $name'),
    );
    await _db.update(
      'exercise_state',
      {
        'weight': defaults.weight,
        'success_threshold': 3,
        'fail_threshold': 2,
        'success_streak': 0,
        'fail_streak': 0,
      },
      where: 'name = ?',
      whereArgs: [name],
    );
    unawaited(_backupNow());
  }

  // ── Backup / restore ───────────────────────────────────────────────────────

  /// Exports all persistent data to external storage as a JSON snapshot.
  Future<void> _backupNow() async {
    final exerciseRows = await _db.query('exercise_state');
    final historyRows = await _db.query('workout_history');
    final settingsRows = await _db.query('settings');
    await BackupService.instance.export({
      'exercise_state': exerciseRows,
      'workout_history': historyRows,
      'settings': settingsRows,
    });
  }

  /// Restores from backup if the local DB is empty (fresh install).
  ///
  /// "Empty" means no workout history and no [last_workout_type] setting.
  Future<void> restoreFromBackupIfNeeded() async {
    final hasHistory =
        (await _db.rawQuery('SELECT COUNT(*) AS c FROM workout_history'))
            .first['c'] as int? ??
        0;
    final hasType = await _getSetting('last_workout_type');
    if (hasHistory > 0 || hasType != null) return; // DB has real data

    final backup = await BackupService.instance.readBackup();
    if (backup == null) return;

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
