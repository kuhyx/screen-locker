import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/sync_status_card.dart';

import '../fake_secure_storage.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  // runAsync steps outside FakeAsync so real I/O (NetworkInterface.list) completes.
  Future<void> _pump(WidgetTester tester, Widget w) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(w);
      // Small real delay lets sqflite + NetworkInterface.list complete.
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
  }

  // The home screen syncs in the background on every open. Left to itself
  // that reaches FlutterSecureStorage, whose platform channel throws under
  // `flutter test`, so every test here would fail on a MissingPluginException
  // that has nothing to do with what it is asserting. Report "not
  // configured" instead: no credentials means no sync tick is attempted.
  Widget _wrap({Future<bool> Function()? configuredProbe}) => MaterialApp(
    theme: buildAppTheme(),
    home: HomeScreen(
      configuredProbe: configuredProbe ?? () async => false,
      clock: () => DateTime(2026, 8, 15, 18),
    ),
  );

  testWidgets('shows Workout Tracker app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Workout Tracker'), findsOneWidget);
  });

  testWidgets('shows Next: Workout A when no workout done', (tester) async {
    await _pump(tester, _wrap());
    expect(find.textContaining('Next: Workout A'), findsOneWidget);
  });

  testWidgets('shows Start Workout A button', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Start Workout A'), findsOneWidget);
  });

  testWidgets('history icon navigates to history screen', (tester) async {
    await _pump(tester, _wrap());
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Progress'), findsOneWidget);
  });

  testWidgets('settings icon navigates to settings screen', (tester) async {
    await _pump(tester, _wrap());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('"Done for today" message shows after saving a session today', (
    tester,
  ) async {
    final today = DateTime.now();
    final dateStr =
        '${today.year}-${today.month.toString().padLeft(2, '0')}'
        '-${today.day.toString().padLeft(2, '0')}';
    // DB writes need the real event loop (the widget-test zone fakes async and
    // would hang sqflite-ffi); run the seed inside runAsync.
    await tester.runAsync(
      () => StorageService.instance.saveSession(
        date: dateStr,
        workoutType: 'A',
        durationSeconds: 1800,
        succeeded: true,
        json: '{"exercises":[]}',
      ),
    );
    await _pump(tester, _wrap());
    expect(find.text('Done for today!'), findsOneWidget);
  });

  testWidgets('manual-workout icon navigates to the manual form', (
    tester,
  ) async {
    installFakeSecureStorage(); // ManualWorkoutScreen loads its sync budget
    await _pump(tester, _wrap());
    await tester.tap(find.byIcon(Icons.edit_note));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Log Manual Workout'), findsOneWidget);
  });

  testWidgets('starting a workout navigates to the workout screen', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.tap(find.text('Start Workout A'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('Workout A'), findsWidgets);
  });

  testWidgets('an active session auto-resumes into the workout screen', (
    tester,
  ) async {
    await tester.runAsync(
      () => StorageService.instance.saveActiveSession({
        'workoutType': 'A',
        'startTime': DateTime.now().toIso8601String(),
        'exercises': <dynamic>[],
      }),
    );
    await _pump(tester, _wrap());
    await tester.pump(const Duration(milliseconds: 300));
    // The post-frame auto-resume pushed the workout screen.
    expect(find.textContaining('Workout A'), findsWidgets);
  });

  testWidgets('active session shows Resume, returns (98) and re-enters (153)', (
    tester,
  ) async {
    // A fully-formed active session so WorkoutScreen restores cleanly (its
    // _restoreFromSaved expects startTimeMs + per-exercise tapped/doneReps).
    await tester.runAsync(
      () => StorageService.instance.saveActiveSession({
        'workoutType': 'A',
        'startTimeMs': DateTime.now().millisecondsSinceEpoch,
        'tapped': [for (final e in workoutA) List<bool>.filled(e.sets, false)],
        'doneReps': [
          for (final e in workoutA) List<int>.filled(e.sets, e.reps),
        ],
        'warmupTapped': List<bool>.filled(workoutA.length, false),
      }),
    );
    // Drive the whole first-load + post-frame auto-resume push on the real loop
    // (auto-resume awaits getCurrentExercises, which hangs under FakeAsync).
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap());
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump(); // fire the post-frame auto-resume callback
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(WorkoutScreen), findsOneWidget);

    // Return to home; auto-resume is now consumed so the Resume button shows.
    await tester.runAsync(() async {
      tester.state<NavigatorState>(find.byType(Navigator).last).pop();
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(WorkoutScreen), findsNothing);
    expect(find.text('Resume Workout'), findsOneWidget);

    // Tapping Resume invokes onResume -> _openWorkout(resume:true) (line 153).
    await tester.runAsync(() async {
      await tester.tap(find.text('Resume Workout'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(WorkoutScreen), findsOneWidget);
  });

  testWidgets('returning from settings reloads the home screen', (
    tester,
  ) async {
    installFakeSecureStorage(); // SettingsScreen reads the sync token on init
    await _pump(tester, _wrap());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Settings'), findsOneWidget);

    // Pop back; the trailing _load() (line 135) needs the real loop for DB I/O.
    await tester.runAsync(() async {
      tester.state<NavigatorState>(find.byType(Navigator).last).pop();
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Workout Tracker'), findsOneWidget);
  });

  group('sync status card', () {
    testWidgets('an unconfigured device is warned before it works out', (
      tester,
    ) async {
      await _pump(tester, _wrap(configuredProbe: () async => false));
      expect(find.byType(SyncStatusCard), findsOneWidget);
      expect(find.text('Not connected to sync'), findsOneWidget);
    });

    testWidgets('the card sits ABOVE the workout card', (tester) async {
      await _pump(tester, _wrap(configuredProbe: () async => false));
      // The whole point of the placement: the warning has to be read before
      // the workout starts, not discovered after it failed to count.
      final cardY = tester.getTopLeft(find.byType(SyncStatusCard)).dy;
      final workoutY = tester.getTopLeft(find.text('Start Workout A')).dy;
      expect(cardY, lessThan(workoutY));
    });

    testWidgets('a failing sync surfaces the reason on the card', (
      tester,
    ) async {
      installFakeSecureStorage();
      await _pump(
        tester,
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(
            configuredProbe: () async => true,
            syncService: _FailingSyncService(),
            clock: () => DateTime(2026, 8, 15, 18),
          ),
        ),
      );
      expect(find.text('Sync failed'), findsOneWidget);
      expect(find.textContaining('no network'), findsOneWidget);
    });

    testWidgets('a phone that has not synced for days says so, before the tick',
        (tester) async {
      // Regression: computing the status only AFTER the tick made
      // SyncState.outOfDate unreachable in the running app -- a success
      // stamps the time (age 0 -> Synced) and a failure shows Sync failed,
      // so a stale phone silently looked healthy.
      installFakeSecureStorage();
      final now = DateTime(2026, 8, 15, 18);
      await tester.runAsync(() async {
        await StorageService.instance.markSyncedNow(
          now.subtract(const Duration(days: 3)),
        );
      });
      await _pump(
        tester,
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(
            configuredProbe: () async => true,
            syncService: _HangingSyncService(),
            clock: () => now,
          ),
        ),
      );
      expect(find.text('Sync out of date'), findsOneWidget);
      expect(find.textContaining('3d ago'), findsOneWidget);
    });

    testWidgets('Set up sync opens Settings so the user can fix it', (
      tester,
    ) async {
      installFakeSecureStorage(); // SettingsScreen reads the token on init
      await _pump(tester, _wrap(configuredProbe: () async => false));
      await tester.tap(find.text('Set up sync'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      // The card must lead somewhere: telling the user sync is broken and
      // leaving them to find Settings is the silence this whole card fixes.
      expect(find.text('Settings'), findsOneWidget);

      // Coming back re-checks sync, so connecting there clears the card
      // without needing an app restart.
      await tester.runAsync(() async {
        tester.state<NavigatorState>(find.byType(Navigator).last).pop();
        await Future<void>.delayed(const Duration(milliseconds: 300));
      });
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('Workout Tracker'), findsOneWidget);
    });

    testWidgets('Retry runs another sync tick', (tester) async {
      installFakeSecureStorage();
      var ticks = 0;
      await _pump(
        tester,
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(
            configuredProbe: () async => true,
            syncService: _CountingSyncService(() => ticks++),
            clock: () => DateTime(2026, 8, 15, 18),
          ),
        ),
      );
      expect(ticks, 1); // the automatic tick on open
      await tester.runAsync(() async {
        await tester.tap(find.text('Retry'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pump();
      expect(ticks, 2);
    });

    testWidgets('a successful sync stamps the time and shows Synced', (
      tester,
    ) async {
      installFakeSecureStorage();
      final now = DateTime(2026, 8, 15, 18);
      await _pump(
        tester,
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(
            configuredProbe: () async => true,
            syncService: _OkSyncService(),
            clock: () => now,
          ),
        ),
      );
      expect(find.textContaining('Synced'), findsOneWidget);
      // The timestamp must actually persist, or the card would go stale
      // again on the very next open. Read it inside runAsync: the DB is real
      // I/O, and awaiting it under FakeAsync hangs the test.
      DateTime? stamped;
      await tester.runAsync(() async {
        stamped = await StorageService.instance.getLastSyncedAt();
      });
      expect(stamped, now);
    });
  });
}

/// A sync service whose tick always fails, with a reason worth showing.
class _FailingSyncService extends WorkoutSyncService {
  @override
  Future<PushResult> syncNow() async =>
      const PushResult(pushed: false, reason: 'sync failed: no network');
}

/// A sync service whose tick always succeeds.
class _OkSyncService extends WorkoutSyncService {
  @override
  Future<PushResult> syncNow() async =>
      const PushResult(pushed: true, reason: 'synced');
}

/// A sync service whose tick never resolves, holding the card on whatever
/// the persisted state said — which is how a real slow network behaves.
class _HangingSyncService extends WorkoutSyncService {
  @override
  Future<PushResult> syncNow() => Completer<PushResult>().future;
}

/// A sync service that counts how many ticks it was asked for.
class _CountingSyncService extends WorkoutSyncService {
  _CountingSyncService(this.onTick);

  /// Called once per [syncNow].
  final void Function() onTick;

  @override
  Future<PushResult> syncNow() async {
    onTick();
    // Fail, so the card keeps offering Retry instead of collapsing to the
    // button-less healthy state after the first tick.
    return const PushResult(pushed: false, reason: 'sync failed: offline');
  }
}
