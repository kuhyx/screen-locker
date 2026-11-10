// Runs in backup.json and the user export: the `runs` / `run_points` half of
// both, written and merged by one code path.
//
// A `part` of StorageService (it needs `_db`). The generic table merge cannot
// be reused: it strips every `id` column and falls back to a progression
// event key, which would store runs with NULL ids.
part of 'storage_service.dart';

/// Runs as portable rows.
extension StorageServiceRunsTransfer on StorageService {
  /// Every run as a `runs` row plus `points`: ONE compact JSON string of
  /// `[time_ms, lat, lon, alt, distance_m]` rows. A string, not nested lists,
  /// so pretty-printing the document does not put every fix on its own line
  /// (a year of runs would otherwise be tens of MB, re-encoded on every
  /// backup).
  ///
  /// [appOnly] leaves the RunnerUp history out: it is reproducible from the
  /// PC, so the automatic backup carries only what exists nowhere else.
  Future<List<Map<String, Object?>>> _runsForTransfer({
    required bool appOnly,
  }) async {
    final rows = await _db.query(
      'runs',
      where: appOnly ? "source = 'app'" : null,
      orderBy: 'started_at, id',
    );
    return [
      for (final row in rows)
        {...row, 'points': await _encodePoints(row['id']! as String)},
    ];
  }

  Future<String> _encodePoints(String runId) async {
    final points = await _db.query(
      'run_points',
      where: 'run_id = ?',
      whereArgs: [runId],
      orderBy: 'seq',
    );
    return jsonEncode([
      for (final p in points)
        [p['time_ms'], p['lat'], p['lon'], p['alt'], p['distance_m']],
    ]);
  }

  /// Merges transferred [raw] runs into the database and returns how many
  /// were new. Idempotent: a run whose id OR TCX hash is already stored is
  /// left alone (and so are its points); a malformed entry is counted and
  /// skipped, never fatal. An imported run is stored as `never` whatever the
  /// file claims, since the table's CHECK would reject anything else.
  Future<int> _mergeRuns(Transaction txn, Object? raw) async {
    if (raw is! List) {
      if (raw != null) _warnSkipped('runs', 1);
      return 0;
    }
    final known = await txn.query('runs', columns: ['id', 'tcx_sha256']);
    final ids = {for (final r in known) r['id']! as String};
    final shas = {for (final r in known) r['tcx_sha256']! as String};
    var written = 0;
    var malformed = 0;
    for (final entry in raw) {
      final parsed = entry is Map<String, dynamic> ? _parseRun(entry) : null;
      if (parsed == null) {
        malformed++;
        continue;
      }
      final (row, points) = parsed;
      final id = row['id']! as String;
      final sha = row['tcx_sha256']! as String;
      if (ids.contains(id) || shas.contains(sha)) continue;
      ids.add(id);
      shas.add(sha);
      await txn.insert('runs', row);
      final batch = txn.batch();
      for (final (seq, p) in points.indexed) {
        batch.insert('run_points', {
          'run_id': row['id'],
          'seq': seq,
          'time_ms': p[0],
          'lat': p[1],
          'lon': p[2],
          'alt': p[3],
          'distance_m': p[4],
        });
      }
      await batch.commit(noResult: true);
      written++;
    }
    if (malformed > 0) _warnSkipped('runs', malformed);
    return written;
  }

  /// The `runs` row and decoded points of [e], or null when it is malformed.
  (Map<String, Object?>, List<List<Object?>>)? _parseRun(
    Map<String, dynamic> e,
  ) {
    try {
      final source = RunSource.fromStorageKey(e['source'] as String);
      final state = source == RunSource.runnerupImport
          ? RunUploadState.never
          : RunUploadState.fromStorageKey(e['upload_state'] as String);
      final points = [
        for (final p in jsonDecode(e['points'] as String) as List<dynamic>)
          [
            (p as List<dynamic>)[0] as int,
            (p[1] as num).toDouble(),
            (p[2] as num).toDouble(),
            (p[3] as num?)?.toDouble(),
            (p[4] as num).toDouble(),
          ],
      ];
      final sport = RunSport.fromTcxName(e['sport'] as String)!.tcxName;
      final id = e['id'] as String;
      final sha = e['tcx_sha256'] as String;
      if (id.isEmpty || sha.isEmpty) return null;
      return (
        {
          'id': id,
          'sport': sport,
          'started_at': e['started_at'] as int,
          'total_seconds': e['total_seconds'] as int,
          'distance_m': (e['distance_m'] as num).toDouble(),
          'source': source.storageKey,
          'upload_state': state.storageKey,
          'tcx_filename': e['tcx_filename'] as String,
          'tcx_sha256': sha,
        },
        points,
      );
    } on Object {
      // Wrong shape, unknown enum key, or a points string that is not JSON:
      // the caller counts it and logs the total via _warnSkipped.
      return null;
    }
  }
}
