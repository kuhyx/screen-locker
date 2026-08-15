// The history chart, the per-exercise drill-down, and PC-synced rows.
//
// Split out of history_screen_test.dart, which keeps the list and tile tests.
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/history_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_secure_storage.dart';
import '_history_test_fixtures.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    // HistoryScreen pulls the PC's synced workouts, which reads the sync token
    // from secure storage — fake it so tests never touch the OS keystore.
    // No token => not configured => no network, and an empty synced list.
    installFakeSecureStorage();
  });

  testWidgets('chart renders with enough data points', (tester) async {
    final json = jsonEncode({
      'exercises': [
        {
          'name': 'Squat',
          'targetSets': 3,
          'targetReps': 5,
          'targetWeight': 20.0,
          'warmupDone': false,
          'succeeded': true,
          'sets': [],
        },
      ],
    });
    for (var i = 1; i <= 3; i++) {
      await seedSession(tester, json, date: '2024-06-0$i');
    }
    await pumpHistory(tester, wrapHistory());
    expect(find.byType(HistoryScreen), findsOneWidget);
  });

  // JSON for one session containing [name] at [weight].
  String _exerciseSessionJson(
    String name,
    double weight, {
    required bool ok,
    required bool warmup,
    required bool withSets,
  }) {
    return jsonEncode({
      'exercises': [
        {
          'name': name,
          'targetSets': 3,
          'targetReps': 5,
          'targetWeight': weight,
          'warmupDone': warmup,
          'succeeded': ok,
          'sets': withSets
              ? [
                  {
                    'targetReps': 5,
                    'doneReps': 5,
                    'weight': weight,
                    'succeeded': true,
                  },
                  {
                    'targetReps': 5,
                    'doneReps': 4,
                    'weight': weight,
                    'succeeded': false,
                  },
                ]
              : <Map<String, dynamic>>[],
        },
      ],
    });
  }

  testWidgets('selecting an exercise shows the drill-down view', (
    tester,
  ) async {
    // Use a real progression-tracked exercise so getExerciseState is non-null
    // and the streak stats card renders. Three distinct weights on three dates
    // give the weight chart >= 2 points with a real range (painter fully runs).
    final name = workoutA.first.name;
    await seedSession(
      tester,
      _exerciseSessionJson(name, 20, ok: true, warmup: true, withSets: true),
      date: '2024-06-01',
    );
    await seedSession(
      tester,
      _exerciseSessionJson(
        name,
        22.5,
        ok: false,
        warmup: false,
        withSets: false,
      ),
      date: '2024-06-08',
      succeeded: false,
    );
    await seedSession(
      tester,
      _exerciseSessionJson(name, 25, ok: true, warmup: true, withSets: true),
      date: '2024-06-15',
    );

    await pumpHistory(tester, wrapHistory());

    // Open the dropdown and pick the exercise; _pickExercise awaits a DB read,
    // and the menu open/close animation runs on real timers under runAsync, so
    // drive the whole interaction on the real loop.
    await tester.runAsync(() async {
      await tester.tap(find.byType(DropdownButton<String>));
      await Future<void>.delayed(const Duration(milliseconds: 400));
      await tester.pump();
      await tester.tap(find.text(name).last);
      await Future<void>.delayed(const Duration(milliseconds: 400));
      await tester.pump();
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    // Exercise view rendered: chart + streak stats card near the top.
    expect(find.text('WEIGHT OVER TIME'), findsOneWidget);
    expect(find.textContaining('more to'), findsWidgets);

    // Exercise-view calendar month nav (covers its onPrev/onNext closures).
    await tester.tap(find.byIcon(Icons.chevron_right).first);
    await tester.pump();
    await tester.tap(find.byIcon(Icons.chevron_left).first);
    await tester.pump();

    // The session list + name label sit below the fold; scroll to build them.
    await tester.scrollUntilVisible(
      find.text(name.toUpperCase()),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text(name.toUpperCase()), findsOneWidget);
    // Session tiles: warmup marker and reps summary both present.
    expect(find.textContaining('warmup'), findsWidgets);
    expect(find.textContaining('reps:'), findsWidgets);
  });

  testWidgets('chart handles two points on the same date (tRange == 0)', (
    tester,
  ) async {
    // Two sessions on the SAME date give the total chart two points that share
    // a timestamp, exercising the painter's tRange == 0 (centre-x) branch.
    String vol(double w) => jsonEncode({
      'exercises': [
        {
          'name': 'Squat',
          'targetSets': 3,
          'targetReps': 5,
          'targetWeight': w,
          'warmupDone': false,
          'succeeded': true,
          'sets': <Map<String, dynamic>>[],
        },
      ],
    });
    await seedSession(tester, vol(20), date: '2024-06-01');
    await seedSession(tester, vol(40), date: '2024-06-01');
    await pumpHistory(tester, wrapHistory());
    expect(find.byType(HistoryScreen), findsOneWidget);
    expect(find.text('WEIGHT OVER TIME').evaluate(), isEmpty); // total view
  });

  testWidgets('shows the PC-synced workouts the phone has no session for', (
    tester,
  ) async {
    // The PC publishes its whole workout_log.json; without this the two
    // devices show different histories (a RunnerUp run exists only on the PC).
    installFakeSecureStorage(initial: {'sync.token': 'tok'});
    await seedSession(
      tester,
      jsonEncode({
        'exercises': [
          {
            'name': 'Squat',
            'targetSets': 3,
            'targetReps': 5,
            'targetWeight': 40.0,
            'warmupDone': false,
            'succeeded': true,
            'setResults': <Map<String, dynamic>>[],
          },
        ],
      }),
      date: '2026-07-11',
    );
    await pumpHistory(tester, wrapHistory(httpClient: historySyncMock()));

    await tester.scrollUntilVisible(
      find.text('SYNCED FROM PC'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('SYNCED FROM PC'), findsOneWidget);
    expect(find.textContaining('2026-07-13  ·  Run'), findsOneWidget);
    expect(find.textContaining('2026-07-13  ·  Manual'), findsOneWidget);
  });
}
