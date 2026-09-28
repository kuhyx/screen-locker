// When the break service starts: on open for a restored session, on the
// first tap for a fresh one -- the launch opens the workout by itself, and
// just opening the app must not leave a notification behind.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/rep_circle.dart';
import 'package:workout_app/widgets/sync_setup_banner.dart';

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

  int starts() => client.calls.where((c) => c == 'start').length;

  testWidgets('a fresh workout does not start the service on open', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout(breakClient: client));
    expect(starts(), 0);
    expect(client.pushed, isEmpty);
    // Nothing recorded, so nothing saved: backing out leaves no session.
    final saved = await tester.runAsync(
      () => StorageService.instance.loadActiveSession(),
    );
    expect(saved, isNull);
  });

  testWidgets('the first set starts it, once, and re-sends the state', (
    tester,
  ) async {
    await pumpWorkout(tester, wrapWorkout(breakClient: client));
    await tapReal(tester, find.byType(RepCircle).first);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );

    expect(starts(), 1);
    // The push after start carries whatever was tapped while the
    // permission prompt could have been up.
    final afterStart = client.calls.sublist(client.calls.indexOf('start'));
    expect(afterStart, contains('push'));
    expect(client.pushed.last.setsRemaining, 5);

    await tapReal(tester, find.byType(RepCircle).first); // a rep decrement
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    expect(starts(), 1, reason: 'one service per workout screen');
  });

  testWidgets('a warmup is enough to start it', (tester) async {
    await pumpWorkout(tester, wrapWorkout(breakClient: client));
    await tapReal(tester, find.bySemanticsLabel('Squat warmup'));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    expect(starts(), 1);
  });

  testWidgets('a restored session starts it on open', (tester) async {
    await pumpWorkout(
      tester,
      wrapWorkout(savedState: blankSaved(), breakClient: client),
    );
    expect(starts(), 1);
  });

  testWidgets('the sync strip shows only when asked for', (tester) async {
    await pumpWorkout(
      tester,
      MaterialApp(
        theme: buildAppTheme(),
        home: WorkoutScreen(
          workoutType: 'A',
          exercises: testExercises,
          breakClient: client,
          syncNotSetUp: true,
        ),
      ),
    );
    expect(find.byType(SyncSetupBanner), findsOneWidget);
    expect(find.textContaining('will NOT count'), findsOneWidget);

    await pumpWorkout(tester, wrapWorkout(breakClient: client));
    expect(find.byType(SyncSetupBanner), findsNothing);
  });
}
