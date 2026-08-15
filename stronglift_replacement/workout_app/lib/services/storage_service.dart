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
import 'package:workout_app/services/progression_sync_service.dart';

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
