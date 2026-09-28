// An exercise on an injury pause: no sets to tap, Finish does not wait for
// it, the notification skips it, and it is recorded as FAILED.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/break_banner.dart';
import 'package:workout_app/widgets/rep_circle.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

import '../fake_audio_platform.dart';
import '../fake_break_service.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

// Real plan names, so each has a progression-state row to pause.
const _lunge = Exercise(name: 'Dumbbell Lunge', sets: 2, reps: 5, weight: 10);
const _situp = Exercise(name: 'Situp', sets: 2, reps: 5, weight: 5);

Future<void> _pause(String name) async {
  final s = (await StorageService.instance.getExerciseState(name))!;
  await StorageService.instance.setExerciseSettings(
    s.copyWith(pausedUntil: pauseEnd(DateTime.now(), 14), failThreshold: 1),
  );
}

void main() {
  late FakeForegroundBreakClient client;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    installFakeAudioPlatform();
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    client = FakeForegroundBreakClient();
  });

  Future<void> pumpPausedSitup(WidgetTester tester) async {
    await tester.runAsync(() => _pause('Situp'));
    await pumpWorkout(
      tester,
      wrapWorkout(
        exercises: const [_lunge, _situp],
        savedState: blankSaved(const [_lunge, _situp]),
        breakClient: client,
      ),
    );
  }

  testWidgets('the paused exercise shows no sets and says so', (tester) async {
    await pumpPausedSitup(tester);
    expect(find.byType(RepCircle), findsNWidgets(_lunge.sets));
    expect(find.textContaining('Paused — back on'), findsOneWidget);
  });

  testWidgets('Finish unlocks without it, and it is recorded as failed', (
    tester,
  ) async {
    await pumpPausedSitup(tester);
    for (var s = 0; s < _lunge.sets; s++) {
      if (restRunning(tester)) await tapReal(tester, find.text('Skip'));
      await tapReal(tester, find.byType(RepCircle).at(s));
    }
    expect(
      tester.widget<BreakBanner>(find.byType(BreakBanner)).canFinish,
      isTrue,
    );
    // The notification never offers the paused exercise's sets.
    expect(client.pushed.last.setsRemaining, 0);

    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      await tester.tap(find.widgetWithText(TextButton, 'Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(WorkoutSummaryDialog), findsOneWidget);
    expect(find.text('Situp: ✗'), findsOneWidget);

    final situp = await tester.runAsync(
      () => StorageService.instance.getExerciseState('Situp'),
    );
    // failThreshold 1: the one "failure" already stepped the weight down.
    expect(situp!.weight, 7.5);
  });

  testWidgets('pausing mid-rest ends that exercise\'s rest', (tester) async {
    await pumpWorkout(
      tester,
      wrapWorkout(exercises: const [_lunge, _situp], breakClient: client),
    );
    await tapReal(tester, find.byType(RepCircle).first);
    expect(restRunning(tester), isTrue);

    await tapReal(
      tester,
      find.bySemanticsLabel('Dumbbell Lunge progression settings'),
    );
    await tester.pumpAndSettle();
    await tapReal(tester, find.text('Pause'));
    expect(restRunning(tester), isFalse);
    expect(find.text('Resume'), findsOneWidget);

    // Resuming brings the sets back; the tap made before the pause stays.
    await tapReal(tester, find.text('Resume'));
    Navigator.of(tester.element(find.text('Pause'))).pop();
    await tester.pumpAndSettle();
    expect(find.byType(RepCircle), findsNWidgets(4));
    expect(tester.widget<RepCircle>(find.byType(RepCircle).first).tapped, true);
  });

  testWidgets('a notification "done" on a paused exercise is dropped', (
    tester,
  ) async {
    await pumpPausedSitup(tester);
    // Nothing inside the paused exercise is offered as next.
    expect(client.pushed.last.nextExName, 'Dumbbell Lunge');
    expect(client.pushed.last.setsRemaining, _lunge.sets);

    // A stale press aimed at Situp's first set must not record it.
    await tester.runAsync(
      () => BreakIntentQueue(PrefsBreakIntentStore()).enqueue(
        kind: BreakIntentKind.done,
        exIdx: 1,
        setIdx: 0,
        now: DateTime.now(),
      ),
    );
    await tester.runAsync(() async {
      client.onNudge!();
      await Future<void>.delayed(const Duration(milliseconds: 400));
    });
    await tester.pump();
    final saved = await tester.runAsync(
      () => StorageService.instance.loadActiveSession(),
    );
    // Applying it would have tapped the set and saved the session.
    expect(saved, isNull);
  });
}
