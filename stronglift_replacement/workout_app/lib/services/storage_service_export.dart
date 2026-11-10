// User-owned export. Skips active_session and keystore secrets: the file
// travels through a share sheet. Same keys as the automatic backup.json.
// The merge-import half lives in storage_service_import.dart.
part of 'storage_service.dart';

/// Marks a document as a workout_app export.
const kExportFormat = 'workout_app-export';

/// The format written now. Version 2 adds `updated_at` to `exercise_state` and
/// `settings` rows plus `manual_workouts`; version 3 adds `runs` (with their
/// points); version 1 and 2 files still import.
const kExportVersion = 3;

const _exportTables = [
  'workout_history',
  'progression_events',
  'exercise_state',
  'settings',
];

/// Export to one plain JSON document.
extension StorageServiceExport on StorageService {
  /// Every user-data table, minus local AUTOINCREMENT ids.
  ///
  /// `manual_workouts` is the remote crdt_sync manual log in wire format
  /// (`Record.toJson`, tombstones included). When the remote cannot be read
  /// (offline, not signed in) the export still succeeds: `manual_workouts` is
  /// null and `manual_workouts_skipped` is true, so a file never claims "no
  /// manual workouts" when it merely could not look.
  Future<Map<String, dynamic>> exportData() async {
    List<Map<String, Object?>> withoutId(List<Map<String, Object?>> rows) => [
      for (final row in rows) Map.of(row)..remove('id'),
    ];
    final settings = await _db.query('settings', orderBy: 'key');
    final manual = await _readManualLog();
    return {
      'format': kExportFormat,
      'version': kExportVersion,
      'exported_at': DateTime.now().toIso8601String(),
      'exercise_state': await _db.query('exercise_state', orderBy: 'name'),
      'workout_history': withoutId(
        await _db.query('workout_history', orderBy: 'date, id'),
      ),
      'progression_events': withoutId(
        await _db.query('progression_events', orderBy: 'at, id'),
      ),
      'settings': [
        for (final row in settings)
          if (!_isPerInstallSetting(row['key']! as String)) row,
      ],
      'runs': await _runsForTransfer(appOnly: false),
      'manual_workouts': manual == null
          ? null
          : [
              for (final id in manual.keys.toList()..sort())
                manual[id]!.toJson(),
            ],
      'manual_workouts_skipped': manual == null,
    };
  }

  Future<Log?> _readManualLog() async {
    try {
      return await StorageService.manualWorkouts.read();
    } on Object catch (error) {
      debugPrint('WorkoutApp: manual workouts NOT exported: $error');
      return null;
    }
  }
}

// Per-install sync bookkeeping: importing it would block a new install's
// Firebase pull and hide its out-of-date card.
bool _isPerInstallSetting(String key) =>
    key == StorageServiceBackup._progressionSyncedKey ||
    key == StorageServiceBackup._lastSyncedAtKey;
