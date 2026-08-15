import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  // ── Workout type ───────────────────────────────────────────────────────────

  group('resetExerciseToDefaults', () {
    test('restores default weight and thresholds', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseWeight(name, 99.0);
      await _svc.resetExerciseToDefaults(name);
      final state = await _svc.getExerciseState(name);
      expect(state!.weight, workoutA.first.weight);
      expect(state.successThreshold, 3);
      expect(state.failThreshold, 2);
    });

    test('throws for unknown exercise name', () async {
      await expectLater(
        _svc.resetExerciseToDefaults('Ghost Exercise'),
        throwsException,
      );
    });
  });

  // ── init is idempotent ─────────────────────────────────────────────────────

  test('init returns same instance when called twice', () async {
    final a = await StorageService.init();
    final b = await StorageService.init();
    expect(identical(a, b), isTrue);
  });

  // ── Schema migration (v1 → v3) ──────────────────────────────────────────────
}
