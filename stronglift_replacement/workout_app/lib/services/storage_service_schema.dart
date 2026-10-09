// Schema creation, migration, and seeding.
//
// Runs once at open; nothing else touches these tables' shape.
// See storage_service_backup.dart for why these are `part` extensions.
part of 'storage_service.dart';

/// The v6 rest-length columns, shared by create and migrate.
const _restColumns =
    'rest_success_secs INTEGER NOT NULL DEFAULT $kDefaultRestSuccessSecs, '
    'rest_fail_secs INTEGER NOT NULL DEFAULT $kDefaultRestFailSecs, '
    'rest_warmup_secs INTEGER NOT NULL DEFAULT $kDefaultRestWarmupSecs';

/// The v7 audit trail of target changes, shared by create and migrate.
///
/// Only manual deloads land here so far (see `manual_deload.dart`); finished
/// workouts still move targets silently. `at` is local ISO-8601, the same
/// format `workout_history.date` uses.
const _progressionEventsTable = '''
  CREATE TABLE IF NOT EXISTS progression_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    exercise TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    from_weight REAL NOT NULL,
    from_reps INTEGER NOT NULL,
    to_weight REAL NOT NULL,
    to_reps INTEGER NOT NULL
  )
''';

/// Schema creation, migration, and seeding.
extension StorageServiceSchema on StorageService {
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
        fail_threshold INTEGER NOT NULL DEFAULT 2,
        progression_mode TEXT NOT NULL DEFAULT 'weight',
        reps_high INTEGER NOT NULL DEFAULT $kDefaultRepsHigh,
        reps_low INTEGER NOT NULL DEFAULT $kDefaultRepsLow,
        has_warmup INTEGER,
        paused_until TEXT,
        $_restColumns
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
    await db.execute(_progressionEventsTable);
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
    if (oldVersion < 4) {
      // has_warmup is left NULL: that reads as the plan's default (see
      // planHasWarmup), so existing rows keep exactly the warmups they had.
      for (final column in [
        "progression_mode TEXT NOT NULL DEFAULT 'weight'",
        'reps_high INTEGER NOT NULL DEFAULT $kDefaultRepsHigh',
        'reps_low INTEGER NOT NULL DEFAULT $kDefaultRepsLow',
        'has_warmup INTEGER',
      ]) {
        await db.execute('ALTER TABLE exercise_state ADD COLUMN $column');
      }
    }
    if (oldVersion < 5) {
      // NULL = not paused.
      await db.execute(
        'ALTER TABLE exercise_state ADD COLUMN paused_until TEXT',
      );
    }
    if (oldVersion < 6) {
      // NOT NULL with a default, so every existing row -- and every v5 row a
      // raw backup restore inserts later -- gets the old fixed rests.
      for (final column in _restColumns.split(', ')) {
        await db.execute('ALTER TABLE exercise_state ADD COLUMN $column');
      }
    }
    if (oldVersion < 7) {
      // A new table, nothing to backfill: deloads before v7 left no trace.
      await db.execute(_progressionEventsTable);
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
          'progression_mode': ProgressionMode.weight.storageKey,
          'reps_high': kDefaultRepsHigh,
          'reps_low': kDefaultRepsLow,
          'has_warmup': ex.hasWarmup ? 1 : 0,
          'rest_success_secs': kDefaultRestSuccessSecs,
          'rest_fail_secs': kDefaultRestFailSecs,
          'rest_warmup_secs': kDefaultRestWarmupSecs,
        });
      }
    }
  }

  // coverage:ignore-start
  // Platform-channel / filesystem edge: Android answers from the sqflite
  // plugin, Linux desktop has no such plugin and uses an XDG directory under
  // the FFI factory wired up in main().
  Future<String> _databaseDirectory() async {
    if (Platform.isLinux) {
      final dir = await getApplicationSupportDirectory();
      return dir.path;
    }
    return await getDatabasesPath();
  }
  // coverage:ignore-end

  // ── Settings ───────────────────────────────────────────────────────────────
}
