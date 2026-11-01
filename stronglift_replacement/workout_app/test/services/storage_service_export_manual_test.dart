import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/manual_workout_port.dart';
import 'package:workout_app/services/storage_service.dart';

import '_sync_test_fixtures.dart' show manualRecord;

StorageService get _svc => StorageService.instance;

/// An in-memory stand-in for the remote crdt_sync log.
class _FakePort implements ManualWorkoutPort {
  _FakePort(this.log, {this.throwOnRead = false});

  /// Null = offline / not signed in.
  Log? log;
  final bool throwOnRead;
  int pushes = 0;

  @override
  Future<Log?> read() async {
    if (throwOnRead) throw StateError('network down');
    return log;
  }

  @override
  Future<bool> push(Log records) async {
    if (log == null) return false;
    pushes++;
    log = mergeLogs(log!, records);
    return true;
  }
}

/// Records compare payload maps by identity, so compare their wire form.
String _wire(Log? log) => jsonEncode({
  for (final id in (log ?? {}).keys.toList()..sort()) id: log![id]!.toJson(),
});

Future<void> _freshStore(ManualWorkoutPort port) async {
  StorageService.resetForTesting();
  await StorageService.init();
  StorageService.manualWorkouts = port;
}

Future<Map<String, dynamic>> _roundTripped() async =>
    jsonDecode(jsonEncode(await _svc.exportData())) as Map<String, dynamic>;

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  final live = manualRecord('manual:2026-07-13T10:00', 'NEW', 2000);
  final tomb = buildTombstone('manual:2026-07-01T09:00');

  test('export carries the remote manual log in crdt wire format', () async {
    await _freshStore(_FakePort({live.id: live, tomb.id: tomb}));
    final data = await _roundTripped();

    expect(data['manual_workouts_skipped'], false);
    final wire = (data['manual_workouts'] as List).cast<Map<String, dynamic>>();
    expect([for (final w in wire) w['id']], [tomb.id, live.id]);
    expect(wire.last, live.toJson());
    expect(Record.fromJson(wire.first).deleted, true);
  });

  test('offline export succeeds with null and a skipped flag', () async {
    await _freshStore(_FakePort(null));
    final data = await _roundTripped();

    expect(data['manual_workouts'], isNull);
    expect(data['manual_workouts_skipped'], true);
    expect(data['exercise_state'], isNotEmpty);
  });

  test('a port that throws is the same as offline', () async {
    await _freshStore(_FakePort({}, throwOnRead: true));
    final data = await _roundTripped();

    expect(data['manual_workouts'], isNull);
    expect(data['manual_workouts_skipped'], true);
  });

  test('manual workouts round-trip through export and import', () async {
    await _freshStore(_FakePort({live.id: live, tomb.id: tomb}));
    final file = await _roundTripped();

    final target = _FakePort({});
    await _freshStore(target);
    final written = await _svc.importData(file);

    expect(_wire(target.log), _wire({live.id: live, tomb.id: tomb}));
    expect(target.pushes, 1);
    expect(written, greaterThanOrEqualTo(2));
  });

  test('importing twice is the same as importing once', () async {
    await _freshStore(_FakePort({live.id: live, tomb.id: tomb}));
    final file = await _roundTripped();

    final target = _FakePort({});
    await _freshStore(target);
    await _svc.importData(file);
    final once = Map.of(target.log!);
    // A fresh decode: payload maps no longer share identity with the first.
    final again = await _svc.importData(
      jsonDecode(jsonEncode(file)) as Map<String, dynamic>,
    );

    expect(again, 0);
    expect(target.pushes, 1);
    expect(_wire(target.log), _wire(once));
  });

  test('an older remote copy never beats a newer local one', () async {
    final newer = manualRecord(live.id, 'NEWER', 9000);
    final target = _FakePort({newer.id: newer});
    await _freshStore(target);
    await _svc.importData({
      'format': kExportFormat,
      'version': 2,
      'manual_workouts': [live.toJson()],
    });
    expect(_wire(target.log), _wire({newer.id: newer}));
  });

  test(
    'offline import still merges the database and reports skipped',
    () async {
      await _freshStore(_FakePort({live.id: live}));
      final file = await _roundTripped();
      (file['settings'] as List).add({
        'key': 'last_workout_type',
        'value': 'B',
        'updated_at': 5,
      });

      await _freshStore(_FakePort(null));
      final report = await _svc.importDataReport(file);

      expect(report.manualSkipped, true);
      expect(report.manualRecords, 0);
      expect(report.rows, greaterThan(0));
      expect(await _svc.getNextWorkoutType(), 'A');
    },
  );

  test('a null manual_workouts (v2 offline file) imports cleanly', () async {
    final target = _FakePort({});
    await _freshStore(target);
    final report = await _svc.importDataReport({
      'format': kExportFormat,
      'version': 2,
      'manual_workouts': null,
      'manual_workouts_skipped': true,
      'settings': [
        {'key': 'last_workout_type', 'value': 'B', 'updated_at': 5},
      ],
    });
    expect(report.manualSkipped, false);
    expect(target.pushes, 0);
  });

  test('malformed manual entries are skipped, the rest merged', () async {
    final target = _FakePort({});
    await _freshStore(target);
    await _svc.importData({
      'format': kExportFormat,
      'version': 2,
      'manual_workouts': [
        live.toJson(),
        'junk',
        {'id': 3},
      ],
    });
    expect(_wire(target.log), _wire({live.id: live}));
  });
}

Record buildTombstone(String id) => Record(
  id: id,
  fields: const {},
  deleted: true,
  deletedHlc: const Hlc(wallTimeMs: 3000, counter: 0, nodeId: 'phone'),
);
