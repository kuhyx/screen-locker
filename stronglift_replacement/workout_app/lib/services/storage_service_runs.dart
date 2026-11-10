// Recorded and imported runs: the v9 `runs` / `run_points` tables.
//
// A `part` of StorageService for the same reason as the other parts: it needs
// `_db`, and runs must not grow a second storage layer next to the schema.
part of 'storage_service.dart';

/// The v9 tables, shared by create and migrate.
///
/// `tcx_sha256` is UNIQUE so the same export can never be stored twice (an
/// import re-run, or a recorded run that also came back from the PC). The
/// CHECK keeps the one rule that must hold even if app code is wrong: an
/// imported run is never uploaded.
const _runsTables = [
  '''
  CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    total_seconds INTEGER NOT NULL,
    distance_m REAL NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('app', 'runnerup_import')),
    upload_state TEXT NOT NULL
      CHECK (upload_state IN ('pending', 'uploaded', 'never')),
    tcx_filename TEXT NOT NULL,
    tcx_sha256 TEXT NOT NULL UNIQUE,
    CHECK (source <> 'runnerup_import' OR upload_state = 'never')
  )
  ''',
  '''
  CREATE TABLE IF NOT EXISTS run_points (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    time_ms INTEGER NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    alt REAL,
    distance_m REAL NOT NULL,
    PRIMARY KEY (run_id, seq)
  ) WITHOUT ROWID
  ''',
];

/// Run persistence.
extension StorageServiceRuns on StorageService {
  /// Stores [track]; returns false (storing nothing) when a run with the same
  /// [tcxSha256] or id is already there.
  ///
  /// Throws [ArgumentError] for an imported run that is not
  /// [RunUploadState.never].
  Future<bool> insertRun(
    RunTrack track, {
    required String tcxFilename,
    required String tcxSha256,
    required RunUploadState uploadState,
  }) async {
    if (track.source == RunSource.runnerupImport &&
        uploadState != RunUploadState.never) {
      throw ArgumentError.value(
        uploadState,
        'uploadState',
        'an imported run must be RunUploadState.never',
      );
    }
    final added = await _db.transaction((txn) async {
      final clash = await txn.query(
        'runs',
        columns: ['id'],
        where: 'id = ? OR tcx_sha256 = ?',
        whereArgs: [track.id, tcxSha256],
      );
      if (clash.isNotEmpty) return false;
      await txn.insert('runs', {
        'id': track.id,
        'sport': track.sport.tcxName,
        'started_at': track.startedAt.millisecondsSinceEpoch,
        'total_seconds': track.totalSeconds,
        'distance_m': track.distanceM,
        'source': track.source.storageKey,
        'upload_state': uploadState.storageKey,
        'tcx_filename': tcxFilename,
        'tcx_sha256': tcxSha256,
      });
      final batch = txn.batch();
      for (final (seq, p) in track.points.indexed) {
        batch.insert('run_points', {
          'run_id': track.id,
          'seq': seq,
          'time_ms': p.time.millisecondsSinceEpoch,
          'lat': p.latitude,
          'lon': p.longitude,
          'alt': p.altitudeM,
          'distance_m': p.distanceM,
        });
      }
      await batch.commit(noResult: true);
      return true;
    });
    // A recorded run exists nowhere else yet; the RunnerUp history does (PC).
    if (added && track.source == RunSource.app) unawaited(_backupNow());
    return added;
  }

  /// Whether a run with this TCX hash is stored.
  Future<bool> runExistsBySha(String tcxSha256) async => (await _db.query(
    'runs',
    columns: ['id'],
    where: 'tcx_sha256 = ?',
    whereArgs: [tcxSha256],
  )).isNotEmpty;

  /// Every run, newest first, without points.
  Future<List<RunRecord>> listRuns({RunUploadState? uploadState}) async {
    final rows = await _db.query(
      'runs',
      where: uploadState == null ? null : 'upload_state = ?',
      whereArgs: uploadState == null ? null : [uploadState.storageKey],
      orderBy: 'started_at DESC',
    );
    return rows.map((r) => _runFromRow(r, const [])).toList();
  }

  /// The run [id] with its points, or null.
  Future<RunRecord?> getRun(String id) async {
    final rows = await _db.query('runs', where: 'id = ?', whereArgs: [id]);
    if (rows.isEmpty) return null;
    final pointRows = await _db.query(
      'run_points',
      where: 'run_id = ?',
      whereArgs: [id],
      orderBy: 'seq',
    );
    final points = pointRows
        .map(
          (r) => RunPoint(
            time: DateTime.fromMillisecondsSinceEpoch(
              r['time_ms']! as int,
              isUtc: true,
            ),
            latitude: r['lat']! as double,
            longitude: r['lon']! as double,
            altitudeM: r['alt'] as double?,
            distanceM: r['distance_m']! as double,
          ),
        )
        .toList();
    return _runFromRow(rows.first, points);
  }

  /// Moves run [id] to [state]; false when it does not exist.
  ///
  /// An imported run cannot leave [RunUploadState.never] (the table's CHECK
  /// rejects it).
  Future<bool> setRunUploadState(String id, RunUploadState state) async =>
      await _db.update(
        'runs',
        {'upload_state': state.storageKey},
        where: 'id = ?',
        whereArgs: [id],
      ) >
      0;

  /// Deletes run [id] and its points; false when it does not exist.
  Future<bool> deleteRun(String id) async => await _db.transaction((txn) async {
    await txn.delete('run_points', where: 'run_id = ?', whereArgs: [id]);
    return await txn.delete('runs', where: 'id = ?', whereArgs: [id]) > 0;
  });

  RunRecord _runFromRow(Map<String, Object?> r, List<RunPoint> points) =>
      RunRecord(
        track: RunTrack(
          id: r['id']! as String,
          sport: RunSport.fromTcxName(r['sport']! as String)!,
          startedAt: DateTime.fromMillisecondsSinceEpoch(
            r['started_at']! as int,
            isUtc: true,
          ),
          points: points,
          totalSeconds: r['total_seconds']! as int,
          distanceM: r['distance_m']! as double,
          source: RunSource.fromStorageKey(r['source']! as String),
        ),
        uploadState: RunUploadState.fromStorageKey(
          r['upload_state']! as String,
        ),
        tcxFilename: r['tcx_filename']! as String,
        tcxSha256: r['tcx_sha256']! as String,
      );
}
