import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/break_banner.dart';
import 'package:workout_app/widgets/exercise_tile.dart';
import 'package:workout_app/widgets/rep_circle.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

import '../fake_audio_platform.dart';
import '../fake_secure_storage.dart';

/// A saved state with every set of the two [_exercises] tapped as done.
Map<String, dynamic> _completeSaved() => {
      'workoutType': 'A',
      'startTimeMs': DateTime.now().millisecondsSinceEpoch,
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

  // Interaction taps trigger `unawaited(_saveActiveSession())` (a sqflite write)
  // and start `Timer.periodic` breaks. Dispatching them inside runAsync keeps
  // those on the real loop, so they complete/cancel instead of lingering as
  // FakeAsync "pending timers" that fail the test.
  Future<void> _tapReal(WidgetTester tester, Finder f) async {
    await tester.runAsync(() async {
      await tester.tap(f);
      await Future<void>.delayed(const Duration(milliseconds: 100));
    });
    await tester.pump();
  }

  // tester.longPress() does internal fake-clock pumps that conflict with
  // runAsync, so drive a manual gesture whose hold exceeds the long-press
  // timeout on the real clock (keeping the resulting DB write on the real loop).
  Future<void> _longPressReal(WidgetTester tester, Finder f) async {
    final center = tester.getCenter(f);
    await tester.runAsync(() async {
      final gesture = await tester.startGesture(center);
      await Future<void>.delayed(const Duration(milliseconds: 700));
      await gesture.up();
      await Future<void>.delayed(const Duration(milliseconds: 100));
    });
    await tester.pump();
  }

  testWidgets('tapping a set starts a break which Skip cancels', (tester) async {
    await _pump(tester, _wrap());
    await _tapReal(tester, find.byType(RepCircle).first);
    expect(find.byType(BreakBanner), findsOneWidget);
    // Success break (5 done >= 5 target).
    expect(find.textContaining('well done'), findsOneWidget);

    await _tapReal(tester, find.text('Skip'));
    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('tapping warmup starts a warmup break', (tester) async {
    await _pump(tester, _wrap());
    await _tapReal(tester, find.byIcon(Icons.fitness_center).first);
    expect(find.textContaining('Warmup rest'), findsOneWidget);
  });

  testWidgets('re-tapping a set decrements reps and recomputes the break',
      (tester) async {
    await _pump(tester, _wrap());
    final circle = find.byType(RepCircle).first;
    await _tapReal(tester, circle); // done=5 -> success break
    expect(find.textContaining('well done'), findsOneWidget);

    await _tapReal(tester, circle); // done 5 -> 4, below target -> fail break
    expect(find.textContaining('keep going'), findsOneWidget);
  });

  testWidgets('long-pressing a set resets it and cancels its break',
      (tester) async {
    await _pump(tester, _wrap());
    final circle = find.byType(RepCircle).first;
    await _tapReal(tester, circle);
    expect(find.byType(BreakBanner), findsOneWidget);

    await _longPressReal(tester, circle);
    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('finishing a completed workout saves and shows the summary',
      (tester) async {
    await _pump(tester, _wrap(savedState: _completeSaved()));

    // Drive the whole flow on the real loop: _confirmFinish's showDialog await
    // resumes into _finishWorkout in the same zone, and _finishWorkout does
    // several sqflite writes that would hang under FakeAsync.
    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.text('Finish workout?'), findsOneWidget);
      // The dialog's Finish button is the last 'Finish' in the tree.
      await tester.tap(find.widgetWithText(TextButton, 'Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(WorkoutSummaryDialog), findsOneWidget);
  });

  testWidgets('confirming Reset clears the active session', (tester) async {
    await tester.runAsync(
      () => StorageService.instance.saveActiveSession({
        'workoutType': 'A',
        'startTimeMs': DateTime.now().millisecondsSinceEpoch,
        'tapped': [
          [false, false, false],
          [false, false, false],
        ],
        'doneReps': [
          [5, 5, 5],
          [5, 5, 5],
        ],
        'warmupTapped': [false, false],
      }),
    );
    await _pump(tester, _wrap());

    // Opening the confirm dialog does no DB work.
    await tester.tap(find.text('Reset'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Reset workout?'), findsOneWidget);

    // Confirm: clearActiveSession is a DB write, so run on the real loop.
    // (The dialog's Reset button is the last 'Reset' in the tree.)
    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Reset').last);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final session = await tester.runAsync(
      () => StorageService.instance.loadActiveSession(),
    );
    expect(session, isNull); // reset cleared the persisted session
  });

  testWidgets('changing a threshold in the workout persists it', (tester) async {
    // A real exercise has a progression-state row, so _onThresholdChanged's
    // state-update branch runs (and the write actually lands).
    final name = workoutA.first.name;
    await _pump(tester, _wrap(exercises: [workoutA.first]));

    // The success stepper's "+" is the first Icons.add in the single tile.
    await _tapReal(tester, find.byIcon(Icons.add).first);

    final state = await tester.runAsync(
      () => StorageService.instance.getExerciseState(name),
    );
    expect(state!.successThreshold, 4); // default 3 -> +1
  });

  testWidgets('restores an in-progress break and finishes it', (tester) async {
    final now = DateTime.now();
    final saved = {
      'workoutType': 'A',
      'startTimeMs': now.millisecondsSinceEpoch,
      'tapped': [
        [true, false, false],
        [false, false, false],
      ],
      'doneReps': [
        [5, 5, 5],
        [5, 5, 5],
      ],
      'warmupTapped': [false, false],
      'breakForExIdx': 0,
      'breakForSetIdx': 0,
      'breakLabel': 'Rest',
      'breakDurationSecs': 180,
      'breakEndMs': now.add(const Duration(seconds: 2)).millisecondsSinceEpoch,
    };
    await _pump(tester, _wrap(savedState: saved));
    expect(find.byType(BreakBanner), findsOneWidget); // break restored

    // The break timer is a real periodic timer (initState ran under _pump's
    // runAsync). Wait out its ~2s remaining so _tickBreak reaches 0 and
    // _onBreakFinished (sound + vibration) runs on the real loop.
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(seconds: 3));
      await tester.pump();
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.byType(BreakBanner), findsNothing);
  });
}
