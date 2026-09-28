// The launch-time auto-open: a cold start with nothing done today skips the
// home screen and lands on the workout, the way todo lands on the editor.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/done_today.dart';
import 'package:workout_app/services/lock_mode.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/workout_sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/sync_setup_banner.dart';

import '_home_test_fixtures.dart';

/// A configured backend whose merged records are [payloads] -- or which
/// throws [error] instead, as an unreachable repo would.
class _RecordsSyncService extends WorkoutSyncService {
  _RecordsSyncService({this.payloads = const [], this.error});

  final List<Map<String, dynamic>> payloads;
  final Object? error;

  @override
  Future<PushResult> syncNow() async =>
      const PushResult(pushed: false, reason: 'sync failed: offline');

  @override
  Future<List<Map<String, dynamic>>> readMergedWorkoutPayloads() async {
    if (error case final e?) throw e;
    return payloads;
  }
}

Widget _app({WorkoutSyncService? sync, bool configured = false}) => MaterialApp(
  theme: buildAppTheme(),
  home: HomeScreen(syncService: sync, configuredProbe: () async => configured),
);

/// Drives the first load and the post-frame push on the real loop: the load
/// awaits sqflite, which hangs under the widget test's fake async.
Future<void> _launch(WidgetTester tester, Widget app) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(app);
    await Future<void>.delayed(const Duration(milliseconds: 300));
    await tester.pump(); // fire the post-frame auto-open
    await Future<void>.delayed(const Duration(milliseconds: 300));
  });
  await tester.pump();
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  testWidgets('nothing done today: the workout opens without showing home', (
    tester,
  ) async {
    await _launch(tester, _app());
    expect(find.byType(WorkoutScreen), findsOneWidget);
    // No transition: the home card was never built underneath.
    expect(find.text('Start Workout A'), findsNothing);
    // Sync is not set up, and the card that says so was skipped.
    expect(find.byType(SyncSetupBanner), findsOneWidget);
  });

  testWidgets('a workout already in local history keeps home', (tester) async {
    await tester.runAsync(
      () => StorageService.instance.saveSession(
        date: dayKey(DateTime.now()),
        workoutType: 'A',
        durationSeconds: 1800,
        succeeded: true,
        json: '{"exercises":[]}',
      ),
    );
    await _launch(tester, _app());
    expect(find.byType(WorkoutScreen), findsNothing);
    expect(find.text('Done for today!'), findsOneWidget);
  });

  testWidgets('a synced record dated today (a run, a manual log) keeps home', (
    tester,
  ) async {
    final sync = _RecordsSyncService(
      payloads: [
        {'kind': 'runnerup_verified', 'date': dayKey(DateTime.now())},
      ],
    );
    await _launch(tester, _app(sync: sync, configured: true));
    expect(find.byType(WorkoutScreen), findsNothing);
    expect(find.text('Done for today!'), findsOneWidget);
  });

  testWidgets('synced records from other days still open, without banner', (
    tester,
  ) async {
    final sync = _RecordsSyncService(
      payloads: [
        {'kind': 'runnerup_verified', 'date': '2020-01-01'},
      ],
    );
    await _launch(tester, _app(sync: sync, configured: true));
    expect(find.byType(WorkoutScreen), findsOneWidget);
    expect(find.byType(SyncSetupBanner), findsNothing);
  });

  testWidgets('an unreadable backend fails open into the workout', (
    tester,
  ) async {
    final sync = _RecordsSyncService(error: TimeoutException('slow repo'));
    await _launch(tester, _app(sync: sync, configured: true));
    expect(find.byType(WorkoutScreen), findsOneWidget);
  });

  testWidgets('PC lock mode keeps home, where manual logging lives', (
    tester,
  ) async {
    lockModeEnabled = true;
    addTearDown(() => lockModeEnabled = false);
    await _launch(tester, _app());
    expect(find.byType(WorkoutScreen), findsNothing);
    expect(find.text('Start Workout A'), findsOneWidget);
  });

  testWidgets('backing out lands on home, with no session left behind', (
    tester,
  ) async {
    await _launch(tester, _app());
    expect(find.byType(WorkoutScreen), findsOneWidget);

    await tester.runAsync(() async {
      tester.state<NavigatorState>(find.byType(Navigator).last).pop();
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    expect(find.byType(WorkoutScreen), findsNothing);
    // Only the first load decides: the reload after the pop stays on home.
    expect(find.text('Start Workout A'), findsOneWidget);
    final saved = await tester.runAsync(
      () => StorageService.instance.loadActiveSession(),
    );
    expect(saved, isNull);
  });

  testWidgets('the fixtures switch the auto-open off', (tester) async {
    await pumpHome(tester, wrapHome());
    expect(find.byType(WorkoutScreen), findsNothing);
  });
}
