// The screen side of the status-bar notification: describing the workout for
// the service, and applying the presses that come back from it.
//
// The real client reports isSupported == false off Android, so these inject a
// fake one -- otherwise the whole notification path is dead code on the test
// host and none of these rules would ever be exercised.
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
import 'package:workout_app/widgets/rep_circle.dart';

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
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    client = FakeForegroundBreakClient();
  });

  /// Queues presses exactly as the foreground service isolate would.
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

  /// Fires the service's drain nudge and lets the resulting work finish.
  ///
  /// The screen's handler is `unawaited(_drainIntents())`, and draining does
  /// real sqflite and prefs I/O -- so the pump has to happen on the real clock
  /// inside runAsync, exactly like the tap helpers in the fixtures file.
  Future<void> nudge(WidgetTester tester) async {
    await tester.runAsync(() async {
      client.onNudge!();
      await Future<void>.delayed(const Duration(milliseconds: 400));
    });
    await tester.pump();
  }

  testWidgets('describes the workout for the notification on every save', (
    tester,
  ) async {
    await pump(tester);

    expect(client.pushed, isNotEmpty, reason: 'pushed as the service starts');
    var snap = lastPushed();
    expect(snap.workoutType, 'A');
    expect(snap.nextExName, 'Squat');
    expect(snap.nextSetNumber, 1);
    expect(snap.nextTotalSets, 3);
    expect(snap.nextReps, 5);
    expect(snap.setsRemaining, 6);
    expect(snap.hasBreak, isFalse);
    expect(snap.lastExIdx, -1, reason: 'nothing recorded yet');

    await tapReal(tester, find.byType(RepCircle).first);
    snap = lastPushed();
    expect(snap.hasBreak, isTrue);
    expect(snap.setsRemaining, 5);
    expect(snap.nextSetNumber, 2, reason: 'next set of the same exercise');
    expect(snap.lastExIdx, 0);
    expect(snap.lastSetIdx, 0);
  });

  testWidgets('Done from the notification records the set and starts a rest', (
    tester,
  ) async {
    await pump(tester);
    await seed([(BreakIntentKind.done, 0, 0)]);

    await nudge(tester);

    expect(restRunning(tester), isTrue);
    expect(lastPushed().setsRemaining, 5);
  });

  testWidgets('Done during a rest ends the rest first, then records', (
    tester,
  ) async {
    await pump(tester, saved: savedWithBreak(90));
    expect(restRunning(tester), isTrue);

    // In-app, tapping a NEW set mid-break is refused. From the notification it
    // means "I am done resting and done with the set" -- both taps at once.
    await seed([(BreakIntentKind.done, 0, 1)]);
    await nudge(tester);

    expect(lastPushed().setsRemaining, lessThan(5));
  });

  testWidgets('− 1 rep stretches the rest from 3 minutes to 5', (tester) async {
    await pump(tester, saved: savedWithBreak(170));
    expect(find.textContaining('well done'), findsOneWidget);

    await seed([(BreakIntentKind.minusRep, 0, 0)]);
    await nudge(tester);

    expect(find.textContaining('keep going'), findsOneWidget);
    expect(lastPushed().breakDurationSecs, 300);
  });

  testWidgets('Skip break from the notification ends the rest', (tester) async {
    await pump(tester, saved: savedWithBreak(90));
    expect(restRunning(tester), isTrue);

    await seed([(BreakIntentKind.skipBreak, 0, 0)]);
    await nudge(tester);

    expect(restRunning(tester), isFalse);
  });
}
