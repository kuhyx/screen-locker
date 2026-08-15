// Break timing, long-press reset, finishing, and threshold edits.
//
// Split out of workout_screen_test.dart, which keeps the render and
// restore-on-construction tests.
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

  // Interaction taps trigger `unawaited(_saveActiveSession())` (a sqflite write)
  // and start `Timer.periodic` breaks. Dispatching them inside runAsync keeps
  // those on the real loop, so they complete/cancel instead of lingering as
  // FakeAsync "pending timers" that fail the test.

  testWidgets('tapping a set starts a break which Skip cancels', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout());
    await tapReal(tester, find.byType(RepCircle).first);
    expect(find.byType(BreakBanner), findsOneWidget);
    // Success break (5 done >= 5 target).
    expect(find.textContaining('well done'), findsOneWidget);

    await tapReal(tester, find.text('Skip'));
    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('tapping warmup starts a warmup break', (tester) async {
    await pumpWorkout(tester, wrapWorkout());
    await tapReal(tester, find.byIcon(Icons.fitness_center).first);
    expect(find.textContaining('Warmup rest'), findsOneWidget);
  });

  testWidgets('re-tapping a set decrements reps and recomputes the break', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout());
    final circle = find.byType(RepCircle).first;
    await tapReal(tester, circle); // done=5 -> success break
    expect(find.textContaining('well done'), findsOneWidget);

    await tapReal(tester, circle); // done 5 -> 4, below target -> fail break
    expect(find.textContaining('keep going'), findsOneWidget);
  });

  testWidgets('long-pressing a set resets it and cancels its break', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout());
    final circle = find.byType(RepCircle).first;
    await tapReal(tester, circle);
    expect(find.byType(BreakBanner), findsOneWidget);

    await longPressReal(tester, circle);
    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('finishing a completed workout saves and shows the summary', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout(savedState: completeSaved()));

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
    await pumpWorkout(tester, wrapWorkout());

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

  testWidgets('changing a threshold in the workout persists it', (
    tester,
  ) async {
    // A real exercise has a progression-state row, so _onThresholdChanged's
    // state-update branch runs (and the write actually lands).
    final name = workoutA.first.name;
    await pumpWorkout(tester, wrapWorkout(exercises: [workoutA.first]));

    // The success stepper's "+" is the first Icons.add in the single tile.
    await tapReal(tester, find.byIcon(Icons.add).first);

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
    await pumpWorkout(tester, wrapWorkout(savedState: saved));
    expect(find.byType(BreakBanner), findsOneWidget); // break restored

    // The break timer is a real periodic timer (initState ran under pumpWorkout's
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
