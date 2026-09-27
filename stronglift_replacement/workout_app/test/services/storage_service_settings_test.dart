// Per-exercise settings writes and progression per mode, through storage.
// Split from storage_service_modes_test.dart for the 250-line cap.
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

StorageService get _svc => StorageService.instance;

final _yesterday = DateTime.now().subtract(const Duration(days: 1));

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  group('setExerciseSettings', () {
    test('persists mode, rep range, warmup and thresholds', () async {
      final name = workoutA.first.name;
      final s = (await _svc.getExerciseState(name))!;
      await _svc.setExerciseSettings(
        s.copyWith(
          mode: ProgressionMode.doubleProgression,
          repsHigh: 15,
          repsLow: 8,
          hasWarmup: false,
          successThreshold: 1,
          failThreshold: 4,
        ),
      );
      final after = (await _svc.getExerciseState(name))!;
      expect(after.mode, ProgressionMode.doubleProgression);
      expect((after.repsHigh, after.repsLow), (15, 8));
      expect(after.hasWarmup, isFalse);
      expect((after.successThreshold, after.failThreshold), (1, 4));
      // The target itself is untouched until the next finished workout.
      expect((after.weight, after.reps), (s.weight, s.reps));
    });

    test('persists a pause and its resume', () async {
      final s = (await _svc.getExerciseState('Situp'))!;
      await _svc.setExerciseSettings(
        s.copyWith(pausedUntil: DateTime(2026, 10, 11)),
      );
      expect(
        (await _svc.getExerciseState('Situp'))!.pausedUntil,
        DateTime(2026, 10, 11),
      );
      await _svc.setExerciseSettings(s.copyWith(resume: true));
      expect((await _svc.getExerciseState('Situp'))!.pausedUntil, isNull);
    });

    test('reaches the workout through getCurrentExercises', () async {
      final name = workoutA.first.name;
      final s = (await _svc.getExerciseState(name))!;
      await _svc.setExerciseSettings(s.copyWith(hasWarmup: false));
      final exercises = await _svc.getCurrentExercises('A');
      expect(exercises.first.hasWarmup, isFalse);
      expect(exercises[1].hasWarmup, isTrue);
    });
  });

  group('applyProgression per mode', () {
    Future<ExerciseState> run(
      ProgressionMode mode, {
      required bool success,
      required int reps,
      DateTime? last,
    }) async {
      final name = workoutA.first.name;
      final s = (await _svc.getExerciseState(name))!;
      await _svc.setExerciseSettings(
        s.copyWith(mode: mode, successThreshold: 1, failThreshold: 1),
      );
      await _svc.setExerciseReps(name, reps);
      await _svc.setExerciseWeight(name, 10);
      await _svc.applyProgression(
        succeededExercises: {name: success},
        lastWorkoutDate: last ?? _yesterday,
      );
      return (await _svc.getExerciseState(name))!;
    }

    test('reps: success adds a rep', () async {
      final s = await run(ProgressionMode.reps, success: true, reps: 10);
      expect((s.weight, s.reps, s.successStreak), (10, 11, 0));
    });

    test('reps: failure removes a rep', () async {
      final s = await run(ProgressionMode.reps, success: false, reps: 10);
      expect((s.weight, s.reps, s.failStreak), (10, 9, 0));
    });

    test('double: success at n moves up in weight and back to m', () async {
      final s = await run(
        ProgressionMode.doubleProgression,
        success: true,
        reps: 12,
      );
      expect((s.weight, s.reps), (12.5, 6));
    });

    test('double: failure at m moves down in weight and up to n', () async {
      final s = await run(
        ProgressionMode.doubleProgression,
        success: false,
        reps: 6,
      );
      expect((s.weight, s.reps), (7.5, 12));
    });

    test('a week off is one regression step in the active mode', () async {
      final s = await run(
        ProgressionMode.reps,
        success: true,
        reps: 10,
        last: DateTime.now().subtract(const Duration(days: 9)),
      );
      expect((s.weight, s.reps, s.successStreak, s.failStreak), (10, 9, 0, 0));
    });
  });
}
