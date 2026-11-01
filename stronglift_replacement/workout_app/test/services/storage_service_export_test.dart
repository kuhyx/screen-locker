import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

Future<void> _freshStore() async {
  StorageService.resetForTesting();
  await StorageService.init();
}

Future<void> _session(String date, String start, String type) =>
    _svc.saveSession(
      date: date,
      workoutType: type,
      durationSeconds: 1800,
      succeeded: true,
      json: jsonEncode({
        'date': date,
        'start_time': start,
        'workout_type': type,
        'exercises': <Object>[],
      }),
    );

/// The comparable part of an export: everything but the export timestamp.
Future<Map<String, dynamic>> _snapshot() async =>
    (await _svc.exportData())..remove('exported_at');

/// A store with history, an edited target, a deload event and settings.
Future<void> _seedRichStore() async {
  final name = workoutA.first.name;
  await _svc.setExerciseWeight(name, 72.5);
  await _svc.manualDeload(workoutB.last.name, source: DeloadSource.settings);
  await _session('2026-10-01', '2026-10-01T07:00:00.000', 'A');
  await _session('2026-10-03', '2026-10-03T07:05:00.000', 'B');
  await _svc.setLastWorkoutType('B');
  await _svc.markProgressionSynced();
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(_freshStore);

  test('export -> import into an empty store reproduces it', () async {
    await _seedRichStore();
    final original = await _snapshot();
    final file = jsonDecode(jsonEncode(await _svc.exportData()));

    await _freshStore();
    await _svc.importData(file as Map<String, dynamic>);

    expect(await _snapshot(), original);
    expect(original['workout_history'] as List, hasLength(2));
    expect(original['progression_events'] as List, hasLength(1));
  });

  test('per-install sync markers never leave the device', () async {
    await _seedRichStore();
    final keys = [
      for (final row in (await _svc.exportData())['settings'] as List)
        (row as Map)['key'],
    ];
    expect(keys, contains('last_workout_type'));
    expect(keys, isNot(contains('progression_synced_at')));
  });

  test('importing the same file twice is the same as once', () async {
    await _seedRichStore();
    final file = await _svc.exportData();

    await _freshStore();
    await _svc.importData(file);
    final once = await _snapshot();
    final written = await _svc.importData(file);

    expect(written, 0);
    expect(await _snapshot(), once);
  });

  test('import into a non-empty store keeps every existing record', () async {
    await _seedRichStore();
    final file = await _svc.exportData();

    await _freshStore();
    final name = workoutA.first.name;
    await _svc.setExerciseWeight(name, 40);
    await _session('2026-10-20', '2026-10-20T18:00:00.000', 'A');
    await _svc.setLastWorkoutType('A');
    final written = await _svc.importData(file);

    final history = await _svc.getWorkoutHistory();
    expect(history.map((r) => r['date']), [
      '2026-10-20',
      '2026-10-03',
      '2026-10-01',
    ]);
    expect(written, greaterThan(0));
    // Local progression and settings stay: this store is not a fresh install.
    expect((await _svc.getExerciseState(name))!.weight, 40);
    expect(await _svc.getNextWorkoutType(), 'B');
  });

  test('rejects a document that is not a workout_app export', () async {
    expect(
      () => _svc.importData({'days': <Object>[]}),
      throwsA(isA<FormatException>()),
    );
  });
}
