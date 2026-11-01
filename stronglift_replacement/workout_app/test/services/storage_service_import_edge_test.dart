// Import edge cases: junk sections, duplicate manual ids, a throwing port.
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/manual_workout_port.dart';
import 'package:workout_app/services/storage_service.dart';

import '_sync_test_fixtures.dart' show manualRecord;

class _Port implements ManualWorkoutPort {
  _Port({this.throwOnRead = false});

  final bool throwOnRead;
  Log pushed = {};

  @override
  Future<Log?> read() async {
    if (throwOnRead) throw StateError('network down');
    return <String, Record>{};
  }

  @override
  Future<bool> push(Log records) async {
    pushed = mergeLogs(pushed, records);
    return true;
  }
}

Future<void> _freshStore(ManualWorkoutPort port) async {
  StorageService.resetForTesting();
  await StorageService.init();
  StorageService.manualWorkouts = port;
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  const id = 'manual:2026-07-13T10:00';

  test('a manual_workouts section that is not a list is skipped', () async {
    await _freshStore(_Port());
    final written = await StorageService.instance.importData({
      'settings': <Object>[],
      'manual_workouts': 'junk',
    });
    expect(written, 0);
  });

  test('a table section that is not a list is skipped', () async {
    await _freshStore(_Port());
    final written = await StorageService.instance.importData({
      'settings': <Object>[],
      'exercise_state': 'junk',
    });
    expect(written, 0);
  });

  test('a manual id repeated in one file merges to the newer copy', () async {
    final port = _Port();
    await _freshStore(port);
    final older = manualRecord(id, 'OLD', 1000);
    final newer = manualRecord(id, 'NEW', 2000);

    final report = await StorageService.instance.importDataReport({
      'manual_workouts': [older.toJson(), newer.toJson()],
    });

    expect(report.manualRecords, 1);
    expect((port.pushed[id]!.fields['payload']!.$1 as Map)['cost'], 'NEW');
  });

  test('a port that throws on import marks manual workouts skipped', () async {
    await _freshStore(_Port(throwOnRead: true));
    final report = await StorageService.instance.importDataReport({
      'manual_workouts': [manualRecord(id, 'X', 1000).toJson()],
    });
    expect(report.manualSkipped, true);
    expect(report.manualRecords, 0);
  });
}
