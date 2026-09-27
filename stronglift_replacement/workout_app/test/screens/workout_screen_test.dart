import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/break_banner.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/rep_circle.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

import '../fake_audio_platform.dart';
import '../fake_secure_storage.dart';

import '_workout_screen_test_fixtures.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    // WorkoutScreen fires an unawaited WorkoutSyncService().push() on
    // completion, which reads the sync token via FlutterSecureStorage --
    // without this, the unmocked platform channel throws
    // MissingPluginException as an unhandled Future error.
    installFakeSecureStorage();
    // The break-end sound creates a real AudioPlayer; fake its platform
    // channels too, for the same reason as above.
    installFakeAudioPlatform();
  });

  testWidgets('has no app bar: no workout type, no elapsed clock', (
    tester,
  ) async {
    // Dropped 2026-09-27 for room: Reset/Finish live in the rest strip.
    await pumpWorkout(tester, wrapWorkout());
    expect(find.byType(AppBar), findsNothing);
    expect(find.textContaining('Workout A'), findsNothing);
    // The strip's idle countdown is the only 00:00 on screen.
    expect(find.text('00:00'), findsOneWidget);
    expect(find.byType(SafeArea), findsWidgets);
  });

  testWidgets('shows exercise tiles for all exercises', (tester) async {
    await pumpWorkout(tester, wrapWorkout());
    expect(find.byType(ExerciseTile), findsNWidgets(testExercises.length));
  });

  testWidgets('Reset and Finish buttons are present', (tester) async {
    await pumpWorkout(tester, wrapWorkout());
    expect(find.text('Reset'), findsOneWidget);
    expect(find.text('Finish'), findsOneWidget);
  });

  testWidgets('Finish button is disabled when not all sets done', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout());
    final finishButton = tester.widget<TextButton>(
      find.widgetWithText(TextButton, 'Finish'),
    );
    expect(finishButton.onPressed, isNull);
  });

  testWidgets('Reset dialog shows and cancels', (tester) async {
    await pumpWorkout(tester, wrapWorkout());
    await tester.tap(find.text('Reset'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Reset workout?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Reset workout?'), findsNothing);
  });

  testWidgets('tapping a set circle marks it as tapped', (tester) async {
    await pumpWorkout(tester, wrapWorkout());
    final circles = find.byType(RepCircle);
    await tester.tap(circles.first);
    await tester.pump();
    expect(find.byType(ExerciseTile), findsWidgets);
  });

  testWidgets('restores saved state on construction', (tester) async {
    final now = DateTime.now();
    final saved = {
      'workoutType': 'A',
      'startTimeMs': now
          .subtract(const Duration(minutes: 10))
          .millisecondsSinceEpoch,
      'tapped': [
        [true, true, true],
        [true, true, true],
      ],
      'doneReps': [
        [5, 5, 5],
        [5, 5, 5],
      ],
      'warmupTapped': [false, false],
    };
    await pumpWorkout(tester, wrapWorkout(savedState: saved));
    final finishButton = tester.widget<TextButton>(
      find.widgetWithText(TextButton, 'Finish'),
    );
    expect(finishButton.onPressed, isNotNull);
  });

  testWidgets('Finish dialog shows when all sets complete', (tester) async {
    final now = DateTime.now();
    final saved = {
      'workoutType': 'A',
      'startTimeMs': now.millisecondsSinceEpoch,
      'tapped': [
        [true, true, true],
        [true, true, true],
      ],
      'doneReps': [
        [5, 5, 5],
        [5, 5, 5],
      ],
      'warmupTapped': [false, false],
    };
    await pumpWorkout(tester, wrapWorkout(savedState: saved));
    await tester.tap(find.text('Finish'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Finish workout?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pump();
  });
}
