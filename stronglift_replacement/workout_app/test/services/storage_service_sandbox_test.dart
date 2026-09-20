import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  Future<void> logWorkout(String date) => StorageService.instance.saveSession(
    date: date,
    workoutType: 'A',
    durationSeconds: 60,
    succeeded: true,
    json: '{}',
  );

  test('wipeAll empties every table and re-seeds the exercises', () async {
    final storage = StorageService.instance;
    await logWorkout('2026-09-20');
    await storage.setLastWorkoutType('A');
    await storage.saveActiveSession({'workoutType': 'A'});
    await storage.setExerciseWeight('Dumbbell Lunge', 99);

    await storage.wipeAll();

    expect(await storage.getWorkoutHistory(), isEmpty);
    expect(await storage.loadActiveSession(), isNull);
    expect(await storage.getNextWorkoutType(), 'A');
    final lunge = await storage.getExerciseState('Dumbbell Lunge');
    expect(lunge!.weight, workoutA.first.weight);
  });

  test(
    'deleteWorkoutsOn removes only that day and reports the count',
    () async {
      final storage = StorageService.instance;
      await logWorkout('2026-09-20');
      await logWorkout('2026-09-20');
      await logWorkout('2026-09-19');
      expect(await storage.deleteWorkoutsOn(DateTime(2026, 9, 20)), 2);
      expect(await storage.deleteWorkoutsOn(DateTime(2026, 9, 20)), 0);
      expect(await storage.getWorkoutHistory(), hasLength(1));
    },
  );

  test('rest override round-trips and falls back when unset', () async {
    final storage = StorageService.instance;
    expect(await storage.getSandboxRestSecs(5), 5);
    await storage.setSandboxRestSecs(42);
    expect(await storage.getSandboxRestSecs(5), 42);
  });
}
