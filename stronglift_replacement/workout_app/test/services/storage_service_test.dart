import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
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

  group('getNextWorkoutType', () {
    test('returns A when no workout has been done', () async {
      expect(await _svc.getNextWorkoutType(), 'A');
    });

    test('returns B after setting last type to A', () async {
      await _svc.setLastWorkoutType('A');
      expect(await _svc.getNextWorkoutType(), 'B');
    });

    test('returns A after setting last type to B', () async {
      await _svc.setLastWorkoutType('B');
      expect(await _svc.getNextWorkoutType(), 'A');
    });
  });

  // ── Active session ─────────────────────────────────────────────────────────

  group('active session', () {
    test('loadActiveSession returns null when empty', () async {
      expect(await _svc.loadActiveSession(), isNull);
    });

    test('saveActiveSession persists and loadActiveSession retrieves', () async {
      final data = {'workoutType': 'A', 'startTimeMs': 1000};
      await _svc.saveActiveSession(data);
      final loaded = await _svc.loadActiveSession();
      expect(loaded, isNotNull);
      expect(loaded!['workoutType'], 'A');
    });

    test('saveActiveSession replaces previous entry', () async {
      await _svc.saveActiveSession({'v': 1});
      await _svc.saveActiveSession({'v': 2});
      final loaded = await _svc.loadActiveSession();
      expect(loaded!['v'], 2);
    });

    test('clearActiveSession removes the entry', () async {
      await _svc.saveActiveSession({'x': 1});
      await _svc.clearActiveSession();
      expect(await _svc.loadActiveSession(), isNull);
    });
  });

  // ── Exercise state ─────────────────────────────────────────────────────────

  group('getExerciseState', () {
    test('returns state for seeded exercises', () async {
      final state = await _svc.getExerciseState(workoutA.first.name);
      expect(state, isNotNull);
      expect(state!.weight, workoutA.first.weight);
    });

    test('returns null for unknown exercise', () async {
      expect(await _svc.getExerciseState('Unknown Exercise'), isNull);
    });
  });

  group('getAllExerciseStates', () {
    test('returns states for all exercises in both plans', () async {
      final states = await _svc.getAllExerciseStates();
      final allNames = {...workoutA, ...workoutB}.map((e) => e.name).toSet();
      expect(states.map((s) => s.name).toSet(), equals(allNames));
    });
  });

  group('setExerciseThresholds', () {
    test('updates thresholds and verifies', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseThresholds(
        name,
        successThreshold: 5,
        failThreshold: 3,
      );
      final state = await _svc.getExerciseState(name);
      expect(state!.successThreshold, 5);
      expect(state.failThreshold, 3);
    });
  });

  group('setExerciseWeight', () {
    test('updates weight and resets streaks', () async {
      final name = workoutA.first.name;
      await _svc.setExerciseWeight(name, 30.0);
      final state = await _svc.getExerciseState(name);
      expect(state!.weight, 30.0);
      expect(state.successStreak, 0);
      expect(state.failStreak, 0);
    });
  });

  group('getCurrentExercises', () {
    test('returns exercises with state-applied weights for A', () async {
      final exercises = await _svc.getCurrentExercises('A');
      expect(exercises.length, workoutA.length);
    });

    test('returns exercises for B', () async {
      final exercises = await _svc.getCurrentExercises('B');
      expect(exercises.length, workoutB.length);
    });
  });

  // ── Progression ────────────────────────────────────────────────────────────

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
}
