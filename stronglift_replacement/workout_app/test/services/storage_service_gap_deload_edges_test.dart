// Gap deload inputs the happy-path tests never produce: a history row with
// no readable time, and a stored stamp that is not a date.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  final lift = workoutA.first.name;

  test('a row with no readable time counts toward no gap', () async {
    StorageService.resetForTesting();
    await StorageService.init();
    final svc = StorageService.instance;
    await svc.saveSession(
      date: 'not a date',
      workoutType: 'A',
      durationSeconds: 1,
      succeeded: true,
      json: jsonEncode({
        'exercises': [
          {'name': lift},
        ],
      }),
    );
    expect((await svc.sessionMarks())[lift], isNull);
    expect(await svc.applyGapDeloads(now: DateTime(2026, 11, 20)), isEmpty);
  });

  test('an unreadable stamp reads as never deloaded', () async {
    final dir = await Directory.systemTemp.createTemp('gap_stamp');
    addTearDown(() => dir.delete(recursive: true));
    final path = p.join(dir.path, 'w.db');
    StorageService.resetForTesting(dbPath: path);
    await StorageService.init();
    final svc = StorageService.instance;
    await svc.setExerciseWeight(lift, 25);
    // A second connection to the same file: the service exposes no raw
    // write, and a sync pull always parses the stamp first.
    final raw = await databaseFactoryFfi.openDatabase(path);
    await raw.update(
      'exercise_state',
      {'last_deloaded_at': 'garbage'},
      where: 'name = ?',
      whereArgs: [lift],
    );
    await raw.close();
    expect((await svc.getExerciseState(lift))!.lastDeloadedAt, isNull);
  });

  test('the sandbox seed defaults to the real clock', () async {
    StorageService.resetForTesting();
    await StorageService.init();
    final svc = StorageService.instance;
    await svc.seedGapScenarios();
    expect(await svc.applyGapDeloads(), isNotEmpty);
  });
}
