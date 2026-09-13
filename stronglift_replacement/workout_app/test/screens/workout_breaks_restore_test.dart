// Restoring a workout whose rest period was running -- or had already ended --
// while the app was not.
//
// Split out of workout_breaks_test.dart to stay under the repo's 250-line cap.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/break_banner.dart';

import '../fake_audio_platform.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

void main() {
  late FakeAudioRecorder audio;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    audio = installFakeAudioPlatform();
  });

  // ── Restoring a session whose rest period already ended ────────────────────
  //
  // This branch used to be an implicit no-op: `_restoreFromSaved` rearmed the
  // ticker only `if (remaining > 0)`, so a break that ended while the app was
  // dead produced no cue and — worse — no log. "The break never rang" was
  // indistinguishable from "there was no break".

  testWidgets('a break that ended while the app was away still plays its cue', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout(savedState: savedWithBreak(-45)));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump();

    expect(
      audio.resumedSources.where((s) => s.contains('break_end')),
      isNotEmpty,
      reason: 'the rest ended 45s ago, inside the grace window, so the user '
          'should hear the cue they were waiting for',
    );
    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('a long-expired break is not replayed, only logged', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout(savedState: savedWithBreak(-7200)));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump();

    expect(
      audio.resumedSources.where((s) => s.contains('break_end')),
      isEmpty,
      reason: 'two hours late is past the grace window — replaying the sound '
          'would just be startling',
    );
    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('a break still running is restored and keeps counting', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout(savedState: savedWithBreak(90)));

    expect(find.byType(BreakBanner), findsOneWidget);
    expect(find.textContaining('well done'), findsOneWidget);
    expect(
      audio.resumedSources.where((s) => s.contains('break_end')),
      isEmpty,
      reason: 'the rest has not ended yet',
    );
  });

  testWidgets('resuming re-reads the deadline and ends a rest that is due', (
    tester,
  ) async {
    // A backgrounded app gets no ticks, so the countdown is stale the instant
    // it comes back. Waiting for the next tick would delay the cue by a second
    // on a good day and forever on a Dozing phone.
    await pumpWorkout(tester, wrapWorkout(savedState: savedWithBreak(1)));
    expect(find.byType(BreakBanner), findsOneWidget);

    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 1200)),
    );
    audio.clear();
    await tester.runAsync(() async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('resuming with no rest running is harmless', (tester) async {
    await pumpWorkout(tester, wrapWorkout());
    await tester.runAsync(() async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
    expect(find.byType(BreakBanner), findsNothing);
  });

  testWidgets('a dead audio route does not take the workout down with it', (
    tester,
  ) async {
    // The cue is fire-and-forget, but it must still SAY it failed -- a rest
    // that ends in silence is indistinguishable from a timer that never fired.
    final logged = <String>[];
    final previous = debugPrint;
    // Restored inside the body, not in a tearDown: flutter_test asserts that
    // no foundation debug variable is still overridden when the body returns.
    debugPrint = (message, {wrapWidth}) => logged.add(message ?? '');

    audio.failNextPlay = true;
    await pumpWorkout(tester, wrapWorkout(savedState: savedWithBreak(-30)));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump();
    debugPrint = previous;

    expect(
      logged.where((m) => m.contains('break-end sound failed to play')),
      isNotEmpty,
      reason: 'a cue that cannot sound must say so, not fail in silence',
    );
    expect(find.byType(BreakBanner), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
