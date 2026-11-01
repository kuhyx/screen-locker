// Merge-import of a user-owned export; never deletes. See
// storage_service_export.dart for the format.
part of 'storage_service.dart';

/// What an import did; [StorageServiceImport.importData] returns the sum.
typedef ImportReport = ({int rows, int manualRecords, bool manualSkipped});

/// Merge-import from one plain JSON document.
extension StorageServiceImport on StorageService {
  /// Merges [data] in and returns the rows and manual records written.
  Future<int> importData(Map<String, dynamic> data) async {
    final report = await importDataReport(data);
    return report.rows + report.manualRecords;
  }

  /// Merges [data] in and says what happened to each part.
  ///
  /// Logs are matched on content and only appended. `exercise_state` and
  /// `settings` rows (version 2 files) carry `updated_at`: the newer stamp
  /// wins per row, a tie keeps local. A version 1 file has no stamps, so it
  /// keeps the old rule: it wins only on a [looksFreshlyInstalled] store.
  /// `manual_workouts` merge through `mergeLogs` into the remote log; when
  /// the remote is unreachable they are skipped (the rest still merges) and
  /// [ImportReport.manualSkipped] says so. Idempotent.
  Future<ImportReport> importDataReport(Map<String, dynamic> data) async {
    if (!_exportTables.any((t) => data[t] is List)) {
      if (data['manual_workouts'] is! List) {
        throw const FormatException('not a workout_app export');
      }
    }
    final version = data['version'];
    final stamped = version is int && version >= 2;
    final fileWins = !stamped && await looksFreshlyInstalled();
    var rows = 0;
    await _db.transaction((txn) async {
      for (final table in _exportTables) {
        rows += await _mergeTable(txn, table, data[table], fileWins, stamped);
      }
    });
    if (rows > 0) unawaited(_backupNow());
    final manual = await _importManual(data['manual_workouts']);
    return (
      rows: rows,
      manualRecords: manual.written,
      manualSkipped: manual.skipped,
    );
  }

  Future<({int written, bool skipped})> _importManual(Object? raw) async {
    if (raw is! List) {
      if (raw != null) _warnSkipped('manual_workouts', 1);
      return (written: 0, skipped: false);
    }
    final incoming = <String, Record>{};
    var malformed = 0;
    for (final entry in raw) {
      try {
        final record = Record.fromJson(entry as Map<String, dynamic>);
        incoming[record.id] = incoming.containsKey(record.id)
            ? mergeLogs(
                {record.id: incoming[record.id]!},
                {record.id: record},
              )[record.id]!
            : record;
      } on Object {
        malformed++;
      }
    }
    if (malformed > 0) _warnSkipped('manual_workouts', malformed);
    if (incoming.isEmpty) return (written: 0, skipped: false);
    try {
      final port = StorageService.manualWorkouts;
      final current = await port.read();
      if (current == null) return (written: 0, skipped: true);
      final changed = <String, Record>{
        for (final e in incoming.entries)
          if (_addsTo(current[e.key], e.value)) e.key: e.value,
      };
      if (changed.isEmpty) return (written: 0, skipped: false);
      if (!await port.push(changed)) return (written: 0, skipped: true);
      return (written: changed.length, skipped: false);
    } on Object catch (error) {
      debugPrint('WorkoutApp: manual workouts NOT imported: $error');
      return (written: 0, skipped: true);
    }
  }

  Future<int> _mergeTable(
    Transaction txn,
    String table,
    Object? raw,
    bool fileWins,
    bool stamped,
  ) async {
    if (raw is! List) {
      if (raw != null) _warnSkipped(table, 1);
      return 0;
    }
    final columns = {
      for (final c in await txn.rawQuery('PRAGMA table_info($table)'))
        c['name']! as String,
    }..remove('id');
    final keyOf = _identity(table);
    final local = {for (final row in await txn.query(table)) keyOf(row): row};
    final appendOnly = !columns.contains('name') && !columns.contains('key');
    var written = 0;
    var malformed = raw.length - raw.whereType<Map<String, dynamic>>().length;
    for (final entry in raw.whereType<Map<String, dynamic>>()) {
      final row = {
        for (final e in entry.entries)
          if (columns.contains(e.key)) e.key: e.value,
      };
      final key = keyOf(row);
      if (key.isEmpty) malformed++;
      if (key.isEmpty || (table == 'settings' && _isPerInstallSetting(key))) {
        continue;
      }
      final existing = local[key];
      if (existing != null) {
        final replace =
            !appendOnly &&
            (stamped
                ? _stamp(row) > _stamp(existing)
                : fileWins && !row.keys.every((c) => existing[c] == row[c]));
        if (!replace) continue;
      }
      await txn.insert(
        table,
        row,
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
      local[key] = row;
      written++;
    }
    if (malformed > 0) _warnSkipped(table, malformed);
    return written;
  }
}

/// Whether merging [incoming] would change [current]: a new record, a field
/// with a strictly greater HLC, a field [current] lacks, or a new tombstone.
///
/// Decided on HLCs, not `Record ==`: that compares payload maps by identity,
/// so a copy that went through JSON would always look changed and every
/// repeat import would push again.
bool _addsTo(Record? current, Record incoming) {
  if (current == null) return true;
  if (incoming.deleted && !current.deleted) return true;
  for (final f in incoming.fields.entries) {
    final have = current.fields[f.key];
    if (have == null || f.value.$2 > have.$2) return true;
  }
  return false;
}

// A row without a usable stamp is "never edited": 0 loses to any stamp.
int _stamp(Map<String, Object?> row) {
  final v = row['updated_at'];
  return v is num ? v.toInt() : 0;
}

void _warnSkipped(String table, int count) => debugPrint(
  'WorkoutApp: import SKIPPED $count malformed $table entr(y/ies) -- '
  'no identity or not an object; the rest of the file was merged.',
);

const _eventColumns = [
  'at',
  'exercise',
  'kind',
  'source',
  'from_weight',
  'from_reps',
  'to_weight',
  'to_reps',
];

String Function(Map<String, Object?>) _identity(String table) =>
    switch (table) {
      'exercise_state' => (r) => r['name'] as String? ?? '',
      'settings' => (r) => r['key'] as String? ?? '',
      'workout_history' => (r) {
        final key = StorageServiceSessions._sessionKey(
          StorageServiceSessions._decodeJson(r['json']),
        );
        return key.isNotEmpty ? key : '${r['date']}|${r['json']}';
      },
      _ => (r) => [for (final c in _eventColumns) r[c]].join('|'),
    };
