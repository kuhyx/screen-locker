// Schema creation, migration, and seeding.
//
// Runs once at open; nothing else touches these tables' shape.
// See storage_service_backup.dart for why these are `part` extensions.
part of 'storage_service.dart';

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

}
