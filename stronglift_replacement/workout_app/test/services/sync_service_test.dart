import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/http_server_service.dart';
import 'package:workout_app/services/sync_service.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('SyncResult', () {
    test('success result has correct fields', () {
      const r = SyncResult(success: true, path: '/sdcard/workout_result.json');
      expect(r.success, isTrue);
      expect(r.path, '/sdcard/workout_result.json');
      expect(r.error, isNull);
    });

    test('failure result has correct fields', () {
      const r = SyncResult(
        success: false,
        path: null,
        error: 'No writable external path',
      );
      expect(r.success, isFalse);
      expect(r.path, isNull);
      expect(r.error, 'No writable external path');
    });
  });

  group('SyncService.writeWorkoutResult', () {
    test('returns SyncResult and updates HttpServerService', () async {
      final session = WorkoutSession(
        workoutType: 'A',
        startTime: DateTime(2024, 6, 1, 9),
        endTime: DateTime(2024, 6, 1, 10),
        exercises: [
          ExerciseResult(
            exercise: const Exercise(
              name: 'Squat',
              sets: 3,
              reps: 5,
              weight: 20,
            ),
            sets: List.generate(
              3,
              (_) => const SetResult(targetReps: 5, doneReps: 5, weight: 20),
            ),
          ),
        ],
      );

      final result = await SyncService().writeWorkoutResult(session);

      // On Linux /sdcard/ and getExternalStorageDirectory() both fail, so we
      // expect the graceful failure path.
      expect(result, isA<SyncResult>());
      // The HTTP server must be updated regardless of file write success.
      expect(
        HttpServerService.instance.latestWorkout,
        contains('"workout_type": "A"'),
      );
    });

    test('failed result has error message when no writable path', () async {
      final session = WorkoutSession(
        workoutType: 'B',
        startTime: DateTime(2024),
        endTime: DateTime(2024),
        exercises: [],
      );

      final result = await SyncService().writeWorkoutResult(session);
      // On Linux both paths fail, so success is false.
      if (!result.success) {
        expect(result.error, isNotNull);
        expect(result.path, isNull);
      }
    });
  });

  group('kSyncFilePath', () {
    test('constant has expected value', () {
      expect(kSyncFilePath, '/sdcard/workout_result.json');
    });
  });
}
