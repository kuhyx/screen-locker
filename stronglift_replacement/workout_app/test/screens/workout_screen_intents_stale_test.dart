// Notification presses the workout has already moved past, and the service's
// lifetime rules.
//
// Split out of workout_screen_intents_test.dart to stay under the repo's
// 250-line cap; the shared setup is duplicated rather than exported because
// each test file owns its own fakes.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_audio_platform.dart';
import '../fake_break_service.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

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
    SharedPreferencesAsyncPlatform.instance = InMemorySharedPreferencesAsync
        .empty();
    client = FakeForegroundBreakClient();
  });

  Future<void> seed(List<(BreakIntentKind, int, int)> presses) async {
    final queue = BreakIntentQueue(PrefsBreakIntentStore());
    for (final (kind, ex, set) in presses) {
      await queue.enqueue(
        kind: kind,
        exIdx: ex,
        setIdx: set,
        now: DateTime.now(),
      );
    }
  }

  Future<void> pump(WidgetTester tester, {Map<String, dynamic>? saved}) =>
      pumpWorkout(tester, wrapWorkout(savedState: saved, breakClient: client));

  BreakSnapshot lastPushed() => client.pushed.last;

  Future<void> nudge(WidgetTester tester) async {
    await tester.runAsync(() async {
      client.onNudge!();
      await Future<void>.delayed(const Duration(milliseconds: 400));
    });
    await tester.pump();
  }

  group('presses the workout has moved past are dropped, not forced', () {
    Future<void> expectNoChange(
      WidgetTester tester,
      List<(BreakIntentKind, int, int)> presses,
    ) async {
      final before = lastPushed().setsRemaining;
      await seed(presses);
      await nudge(tester);
      expect(lastPushed().setsRemaining, before);
    }

    testWidgets('an exercise index this workout does not have', (tester) async {
        await pump(tester);
      await expectNoChange(tester, [(BreakIntentKind.done, 99, 0)]);
    });

    testWidgets('a set index this exercise does not have', (tester) async {
        await pump(tester);
      await expectNoChange(tester, [(BreakIntentKind.done, 0, 99)]);
    });

    testWidgets('a negative index', (tester) async {
        await pump(tester);
      await expectNoChange(tester, [(BreakIntentKind.minusRep, -1, 0)]);
    });

    testWidgets('Done on a set that is already recorded', (tester) async {
        await pump(tester, saved: savedWithBreak(90));
      await expectNoChange(tester, [(BreakIntentKind.done, 0, 0)]);
    });

    testWidgets('− 1 rep on a set that was never recorded', (tester) async {
        await pump(tester);
      await expectNoChange(tester, [(BreakIntentKind.minusRep, 1, 2)]);
    });

    testWidgets('Skip break with no rest running', (tester) async {
        await pump(tester);
      await expectNoChange(tester, [(BreakIntentKind.skipBreak, 0, 0)]);
    });
  });

  testWidgets('warns on screen when notifications were refused', (
    tester,
  ) async {
    // A foreground service whose POST_NOTIFICATIONS is denied still RUNS but
    // shows nothing -- no alert, no status bar, no error. That is the exact
    // silent failure this whole feature exists to remove, so the user is told.
    client
      ..permissionGranted = false
      ..grantOnRequest = false;
    await pump(tester);

    expect(
      find.textContaining('Notifications are off'),
      findsOneWidget,
    );
  });

  testWidgets('no warning when notifications were allowed', (tester) async {
    await pump(tester);
    expect(find.textContaining('Notifications are off'), findsNothing);
  });

  testWidgets('a press that arrives after the workout is finished is dropped', (
    tester,
  ) async {
    await pump(tester, saved: completeSaved());
    // Whole flow on the real loop: _confirmFinish's showDialog resumes into
    // _finishWorkout, which does several sqflite writes.
    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      await tester.tap(find.widgetWithText(TextButton, 'Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
    });
    await tester.pump();

    // Finishing stops the service, so there is no nudge callback left to
    // fire -- a press can now only arrive via the resume path, e.g. one made
    // moments before the user hit Finish.
    expect(client.onNudge, isNull, reason: 'the service was stopped');

    await seed([(BreakIntentKind.done, 0, 0)]);
    await tester.runAsync(() async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await Future<void>.delayed(const Duration(milliseconds: 400));
    });
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('leaving the screen does NOT stop the service', (tester) async {
    // The back button pops this screen while the workout carries on in the
    // database. Stopping the service here killed the countdown and the
    // notification with it -- silently restoring the original bug. Verified
    // on-device 2026-09-12: BACK took the service down.
    await pump(tester);
    expect(client.calls, contains('start'));

    await tester.runAsync(() async {
      await tester.pumpWidget(const SizedBox.shrink());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });

    expect(
      client.calls,
      isNot(contains('stop')),
      reason: 'the rest deadline must survive leaving the workout screen',
    );
  });

  testWidgets('finishing the workout DOES stop the service', (tester) async {
    await pump(tester, saved: completeSaved());
    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      await tester.tap(find.widgetWithText(TextButton, 'Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
    });
    await tester.pump();
    expect(client.calls, contains('stop'));
  });
}
