// The home screen's sync-status card: state, Retry, and the sync tick.
//
// Split out of home_screen_test.dart, which keeps navigation and the
// workout-start paths.
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
import '_home_test_fixtures.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  group('sync status card', () {
    testWidgets('an unconfigured device is warned before it works out', (
      tester,
    ) async {
      await pumpHome(tester, wrapHome(configuredProbe: () async => false));
      expect(find.byType(SyncStatusCard), findsOneWidget);
      expect(find.text('Not connected to sync'), findsOneWidget);
    });

    testWidgets('the card sits ABOVE the workout card', (tester) async {
      await pumpHome(tester, wrapHome(configuredProbe: () async => false));
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
      await pumpHome(
        tester,
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(
            configuredProbe: () async => true,
            syncService: FailingSyncService(),
            clock: () => DateTime(2026, 8, 15, 18),
          ),
        ),
      );
      expect(find.text('Sync failed'), findsOneWidget);
      expect(find.textContaining('no network'), findsOneWidget);
    });

    testWidgets(
      'a phone that has not synced for days says so, before the tick',
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
        await pumpHome(
          tester,
          MaterialApp(
            theme: buildAppTheme(),
            home: HomeScreen(
              configuredProbe: () async => true,
              syncService: HangingSyncService(),
              clock: () => now,
            ),
          ),
        );
        expect(find.text('Sync out of date'), findsOneWidget);
        expect(find.textContaining('3d ago'), findsOneWidget);
      },
    );

    testWidgets('Set up sync opens Settings so the user can fix it', (
      tester,
    ) async {
      installFakeSecureStorage(); // SettingsScreen reads the token on init
      await pumpHome(tester, wrapHome(configuredProbe: () async => false));
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
      await pumpHome(
        tester,
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(
            configuredProbe: () async => true,
            syncService: CountingSyncService(() => ticks++),
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
      await pumpHome(
        tester,
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(
            configuredProbe: () async => true,
            syncService: OkSyncService(),
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
