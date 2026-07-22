import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

WorkoutSession _session({
  bool allSucceeded = true,
  Duration duration = const Duration(minutes: 45, seconds: 30),
}) {
  final start = DateTime(2024, 6, 1, 9);
  final end = start.add(duration);
  return WorkoutSession(
    workoutType: 'A',
    startTime: start,
    endTime: end,
    exercises: [
      ExerciseResult(
        exercise: const Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20),
        sets: List.generate(
          3,
          (_) => SetResult(
            targetReps: 5,
            doneReps: allSucceeded ? 5 : 3,
            weight: 20,
          ),
        ),
      ),
    ],
  );
}

void main() {
  group('WorkoutSummaryDialog', () {
    testWidgets('shows "Workout Complete!" when fully succeeded', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(),
            syncResult: const SyncResult(
              success: true,
              path: '/sdcard/workout_result.json',
            ),
          ),
        ),
      );
      expect(find.textContaining('Workout Complete'), findsOneWidget);
    });

    testWidgets('shows "Workout Done" when not fully succeeded', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(allSucceeded: false),
            syncResult: const SyncResult(
              success: false,
              path: null,
              error: 'No writable external path',
            ),
          ),
        ),
      );
      expect(find.text('Workout Done'), findsOneWidget);
    });

    testWidgets('shows duration in mm m ss s format for sub-hour workout', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(),
            syncResult: const SyncResult(success: true, path: '/p'),
          ),
        ),
      );
      expect(find.textContaining('45m 30s'), findsOneWidget);
    });

    testWidgets('shows hours in duration for long workouts', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(
              duration: const Duration(hours: 1, minutes: 5, seconds: 3),
            ),
            syncResult: const SyncResult(success: true, path: '/p'),
          ),
        ),
      );
      expect(find.textContaining('1h'), findsOneWidget);
    });

    testWidgets('shows exercise name with check mark on success', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(),
            syncResult: const SyncResult(success: true, path: '/p'),
          ),
        ),
      );
      expect(find.textContaining('Squat: ✓'), findsOneWidget);
    });

    testWidgets('shows exercise name with cross on failure', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(allSucceeded: false),
            syncResult: const SyncResult(
              success: false,
              path: null,
              error: 'err',
            ),
          ),
        ),
      );
      expect(find.textContaining('Squat: ✗'), findsOneWidget);
    });

    testWidgets('shows saved path on sync success', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(),
            syncResult: const SyncResult(
              success: true,
              path: '/sdcard/workout_result.json',
            ),
          ),
        ),
      );
      expect(
        find.textContaining('Saved to /sdcard/workout_result.json'),
        findsOneWidget,
      );
    });

    testWidgets('shows error message on sync failure', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(allSucceeded: false),
            syncResult: const SyncResult(
              success: false,
              path: null,
              error: 'No writable external path',
            ),
          ),
        ),
      );
      expect(
        find.textContaining('Sync failed: No writable external path'),
        findsOneWidget,
      );
    });

    testWidgets('"Back to Home" button pops to first route', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: WorkoutSummaryDialog(
              session: _session(),
              syncResult: const SyncResult(success: true, path: '/p'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Back to Home'));
      await tester.pumpAndSettle();
      // No exception = navigator popped cleanly.
    });
  });
}
