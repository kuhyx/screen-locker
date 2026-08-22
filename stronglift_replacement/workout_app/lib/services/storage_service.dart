/// Persistent storage for exercise progression state using SQLite.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/progression_sync_service.dart';

part 'storage_service_backup.dart';
part 'storage_service_exercises.dart';
part 'storage_service_schema.dart';
part 'storage_service_sessions.dart';

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
    remoteActiveSessionReader = null;
  }

  /// Reads the shared in-progress session from Firebase. Injected because the
  /// real implementation reaches the OS keystore through a platform channel,
  /// which `flutter test` has no binding for — and the resulting failure is an
  /// `Error`, not an `Exception`, so it escapes the usual guards.
  ///
  /// Null means "use the real Firebase reader" (production).
  @visibleForTesting
  static Future<Map<String, dynamic>?> Function()? remoteActiveSessionReader;

  Future<void> _open() async {
    final dbPath =
        _testDbPath ??
        // coverage:ignore-start
        p.join(await _databaseDirectory(), 'workout_app.db');
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
  ///
  /// Then, if the mirror is unavailable too, to Firebase. The mirror is tried
  /// first because it is a local file read; Firebase costs a network round
  /// trip, but it is the only copy that survives a reinstall with storage
  /// permission denied — where `/sdcard` is unreadable by definition.
  Future<Map<String, dynamic>?> loadActiveSession() async {
    final rows = await _db.query('active_session', where: 'id = 1');
    if (rows.isNotEmpty) {
      return jsonDecode(rows.first['json']! as String) as Map<String, dynamic>;
    }
    final mirrored =
        await BackupService.instance.readActiveSession() ??
        await (remoteActiveSessionReader ??
            ProgressionSyncService().readActiveSession)();
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

  /// Returns up to [limit] past sessions, newest first.
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
}
