import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

StorageService get _svc => StorageService.instance;

RunTrack _track({
  String start = '2026-11-09T16:30:00Z',
  RunSource source = RunSource.app,
  RunSport sport = RunSport.running,
}) {
  final t = DateTime.parse(start);
  return RunTrack.started(
    sport: sport,
    startedAt: t,
    totalSeconds: 20,
    distanceM: 27.5,
    source: source,
    points: [
      for (var i = 0; i < 3; i++)
        RunPoint(
          time: t.add(Duration(seconds: i * 10)),
          latitude: 48.8584 + i * 0.0001,
          longitude: 2.2945,
          altitudeM: i == 1 ? null : 31.5,
          distanceM: i * 13.75,
        ),
    ],
  );
}

Future<bool> _insert(
  RunTrack t, {
  RunUploadState state = RunUploadState.pending,
  String? sha,
}) => _svc.insertRun(
  t,
  tcxFilename: tcxFilename(t, utcOffset: Duration.zero),
  tcxSha256: sha ?? tcxSha256(encodeTcx(t)),
  uploadState: state,
);

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  tearDown(StorageService.resetForTesting);

  test('insert then getRun returns the points in order', () async {
    final t = _track();
    expect(await _insert(t), isTrue);
    final rec = (await _svc.getRun(t.id))!;
    expect(rec.uploadState, RunUploadState.pending);
    expect(rec.tcxFilename, 'RunnerUp_2026-11-09-16-30-00_Running.tcx');
    expect(rec.tcxSha256, tcxSha256(encodeTcx(t)));
    expect(rec.track.id, t.id);
    expect(rec.track.sport, RunSport.running);
    expect(rec.track.startedAt, t.startedAt);
    expect(rec.track.totalSeconds, 20);
    expect(rec.track.distanceM, 27.5);
    expect(rec.track.source, RunSource.app);
    expect(rec.track.points, t.points);
  });

  test('getRun of an unknown id is null', () async {
    expect(await _svc.getRun('nope'), isNull);
  });

  test('the same TCX hash or id is stored only once', () async {
    final t = _track();
    expect(await _insert(t, sha: 'aa'), isTrue);
    expect(
      await _insert(_track(start: '2026-11-10T08:00:00Z'), sha: 'aa'),
      isFalse,
    );
    expect(await _insert(t, sha: 'bb'), isFalse);
    expect(await _svc.runExistsBySha('aa'), isTrue);
    expect(await _svc.runExistsBySha('bb'), isFalse);
    expect(await _svc.listRuns(), hasLength(1));
    expect((await _svc.getRun(t.id))!.track.points, hasLength(3));
  });

  test('listRuns is newest first, without points, and can filter', () async {
    await _insert(_track(), sha: '1');
    await _insert(
      _track(start: '2026-11-10T08:00:00Z', sport: RunSport.walking),
      sha: '2',
    );
    await _insert(
      _track(start: '2026-11-08T08:00:00Z', source: RunSource.runnerupImport),
      state: RunUploadState.never,
      sha: '3',
    );
    final all = await _svc.listRuns();
    expect(all.map((r) => r.track.id), [
      '2026-11-10T08:00:00Z',
      '2026-11-09T16:30:00Z',
      '2026-11-08T08:00:00Z',
    ]);
    expect(all.every((r) => r.track.points.isEmpty), isTrue);
    expect(all.first.track.sport, RunSport.walking);
    final pending = await _svc.listRuns(uploadState: RunUploadState.pending);
    expect(pending, hasLength(2));
    final never = await _svc.listRuns(uploadState: RunUploadState.never);
    expect(never.single.track.source, RunSource.runnerupImport);
  });

  test('an imported run can only be stored as never', () async {
    final imported = _track(source: RunSource.runnerupImport);
    await expectLater(_insert(imported), throwsA(isA<ArgumentError>()));
    expect(await _insert(imported, state: RunUploadState.never), isTrue);
    expect(await _svc.listRuns(), hasLength(1));
  });

  test('the table itself rejects an imported run that is not never', () async {
    final imported = _track(source: RunSource.runnerupImport);
    await _insert(imported, state: RunUploadState.never);
    await expectLater(
      _svc.setRunUploadState(imported.id, RunUploadState.uploaded),
      throwsA(isA<DatabaseException>()),
    );
  });

  test('setRunUploadState moves a recorded run and reports misses', () async {
    final t = _track();
    await _insert(t);
    expect(await _svc.setRunUploadState(t.id, RunUploadState.uploaded), isTrue);
    expect((await _svc.getRun(t.id))!.uploadState, RunUploadState.uploaded);
    expect(await _svc.setRunUploadState('nope', RunUploadState.never), isFalse);
  });

  test('deleteRun removes the run and its points', () async {
    final t = _track();
    await _insert(t);
    expect(await _svc.deleteRun(t.id), isTrue);
    expect(await _svc.getRun(t.id), isNull);
    expect(await _svc.deleteRun(t.id), isFalse);
    // Re-inserting works: no orphan points block the primary key.
    expect(await _insert(t), isTrue);
    expect((await _svc.getRun(t.id))!.track.points, hasLength(3));
  });

  test('wipeAll clears runs and their points', () async {
    final t = _track();
    await _insert(t);
    await _svc.wipeAll();
    expect(await _svc.listRuns(), isEmpty);
    expect(await _insert(t), isTrue);
  });

  test('v8 -> v9 migration creates the run tables and keeps data', () async {
    final dir = await Directory.systemTemp.createTemp('runs_v9');
    addTearDown(() => dir.delete(recursive: true));
    final path = p.join(dir.path, 'v8.db');
    StorageService.resetForTesting(dbPath: path);
    await StorageService.init();
    final t = _track();
    await _insert(t);
    StorageService.resetForTesting();

    final raw = await databaseFactory.openDatabase(path);
    await raw.execute('DROP TABLE runs');
    await raw.execute('DROP TABLE run_points');
    await raw.execute('PRAGMA user_version = 8');
    await raw.close();

    StorageService.resetForTesting(dbPath: path);
    await StorageService.init();
    expect(await _svc.listRuns(), isEmpty);
    expect(await _insert(t), isTrue);
    expect((await _svc.getRun(t.id))!.track.points, hasLength(3));
    // Exercise seeding survived: the pre-existing tables are untouched.
    expect(await _svc.getNextWorkoutType(), 'A');
  });
}
