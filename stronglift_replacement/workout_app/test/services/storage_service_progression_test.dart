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

  group('applyProgression', () {
    test('increments successStreak on success below threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 3,
        failThreshold: 2,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.successStreak, (before!.successStreak + 1));
    });

    test('progresses weight when successStreak hits threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 1,
        failThreshold: 2,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      // Weight should increase (if below maxWeight) or reps increase
      if (before!.weight < before.maxWeight) {
        expect(after!.weight, greaterThan(before.weight));
      } else {
        expect(after!.reps, greaterThanOrEqualTo(before.reps + 1));
      }
    });

    test('increments failStreak on failure below threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 3,
        failThreshold: 3,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: false},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.failStreak, (before!.failStreak + 1));
    });

    test('decreases weight when failStreak hits threshold', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 3,
        failThreshold: 1,
      );
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: false},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.weight, lessThanOrEqualTo(before!.weight));
    });

    test('reduces weight after long break (> 7 days)', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseWeight(name, 20.0);
      final before = await _svc.getExerciseState(name);
      await _svc.applyProgression(
        succeededExercises: {name: true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 10)),
      );
      final after = await _svc.getExerciseState(name);
      expect(after!.weight, lessThan(before!.weight));
    });

    test('skips unknown exercise gracefully', () async {
      await _svc.applyProgression(
        succeededExercises: {'Ghost Exercise': true},
        lastWorkoutDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      // No exception thrown — that's the test.
    });
  });

  // ── History ────────────────────────────────────────────────────────────────

  group('workout history', () {
    test('getLastWorkoutDate returns null when empty', () async {
      expect(await _svc.getLastWorkoutDate(), isNull);
    });

    test('saveSession and getLastWorkoutDate', () async {
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'A',
        durationSeconds: 2700,
        succeeded: true,
        json: '{}',
      );
      final date = await _svc.getLastWorkoutDate();
      expect(date, isNotNull);
      expect(date!.year, 2024);
    });

    test('getWorkoutHistory returns rows newest first', () async {
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'A',
        durationSeconds: 1000,
        succeeded: true,
        json: '{}',
      );
      await _svc.saveSession(
        date: '2024-06-02',
        workoutType: 'B',
        durationSeconds: 1200,
        succeeded: false,
        json: '{}',
      );
      final rows = await _svc.getWorkoutHistory(limit: 10);
      expect(rows.first['date'], '2024-06-02');
    });

    test('getWorkoutHistory respects limit', () async {
      for (var i = 0; i < 5; i++) {
        await _svc.saveSession(
          date: '2024-0$i-01',
          workoutType: 'A',
          durationSeconds: 1000,
          succeeded: true,
          json: '{}',
        );
      }
      final rows = await _svc.getWorkoutHistory(limit: 3);
      expect(rows.length, lessThanOrEqualTo(3));
    });

    test('getAllWorkoutDates returns distinct dates', () async {
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'A',
        durationSeconds: 1000,
        succeeded: true,
        json: '{}',
      );
      await _svc.saveSession(
        date: '2024-06-01',
        workoutType: 'B',
        durationSeconds: 1200,
        succeeded: false,
        json: '{}',
      );
      final dates = await _svc.getAllWorkoutDates();
      expect(dates.where((d) => d == '2024-06-01').length, 1);
    });
  });

  // ── Reset to defaults ──────────────────────────────────────────────────────
}
