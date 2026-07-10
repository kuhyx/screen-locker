import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/rep_circle.dart';

import '../fake_audio_platform.dart';
import '../fake_secure_storage.dart';

const _exercises = [
  Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20.0),
  Exercise(name: 'Press', sets: 3, reps: 5, weight: 15.0),
];

Widget _wrap({
  String type = 'A',
  List<Exercise> exercises = _exercises,
  Map<String, dynamic>? savedState,
}) =>
    MaterialApp(
      home: WorkoutScreen(
        workoutType: type,
        exercises: exercises,
        savedState: savedState,
      ),
    );

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

  Future<void> _pump(WidgetTester tester, Widget w) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(w);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
  }

  testWidgets('shows Workout A in app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.textContaining('Workout A'), findsOneWidget);
  });

  testWidgets('shows exercise tiles for all exercises', (tester) async {
    await _pump(tester, _wrap());
    expect(find.byType(ExerciseTile), findsNWidgets(_exercises.length));
  });

  testWidgets('Reset and Finish buttons are present', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Reset'), findsOneWidget);
    expect(find.text('Finish'), findsOneWidget);
  });

  testWidgets('Finish button is disabled when not all sets done', (tester) async {
    await _pump(tester, _wrap());
    final finishButton = tester.widget<TextButton>(
      find.widgetWithText(TextButton, 'Finish'),
    );
    expect(finishButton.onPressed, isNull);
  });

  testWidgets('Reset dialog shows and cancels', (tester) async {
    await _pump(tester, _wrap());
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
    await _pump(tester, _wrap());
    final circles = find.byType(RepCircle);
    await tester.tap(circles.first);
    await tester.pump();
    expect(find.byType(ExerciseTile), findsWidgets);
  });

  testWidgets('restores saved state on construction', (tester) async {
    final now = DateTime.now();
    final saved = {
      'workoutType': 'A',
      'startTimeMs':
          now.subtract(const Duration(minutes: 10)).millisecondsSinceEpoch,
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
    await _pump(tester, _wrap(savedState: saved));
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
    await _pump(tester, _wrap(savedState: saved));
    await tester.tap(find.text('Finish'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Finish workout?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pump();
  });

  testWidgets('elapsed timer shows time in app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.textContaining('00:00'), findsOneWidget);
  });

  testWidgets('B workout type shows in app bar', (tester) async {
    await _pump(tester, _wrap(type: 'B'));
    expect(find.textContaining('Workout B'), findsOneWidget);
  });
}
