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

  testWidgets('shows Progress app bar', (tester) async {
    await pumpHistory(tester, wrapHistory());
    expect(find.text('Progress'), findsOneWidget);
  });

  testWidgets('shows "No workouts yet." when history is empty', (tester) async {
    await pumpHistory(tester, wrapHistory());
    expect(find.text('No workouts yet.'), findsOneWidget);
  });

  testWidgets('shows session rows when history has data', (tester) async {
    final json = jsonEncode({
      'exercises': [
        {
          'name': 'Squat',
          'targetSets': 3,
          'targetReps': 5,
          'targetWeight': 20.0,
          'warmupDone': false,
          'succeeded': true,
          'sets': [
            {'targetReps': 5, 'doneReps': 5, 'weight': 20.0, 'succeeded': true},
          ],
        },
      ],
    });
    await seedSession(tester, json);
    await pumpHistory(tester, wrapHistory());
    expect(find.textContaining('Workout A'), findsWidgets);
  });

  testWidgets('exercise picker shows "Total (all workouts)" initially', (
    tester,
  ) async {
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
    await seedSession(tester, json);
    await pumpHistory(tester, wrapHistory());
    expect(find.textContaining('Total'), findsOneWidget);
  });

  testWidgets('calendar prev/next month navigation works', (tester) async {
    final json = jsonEncode({'exercises': []});
    await seedSession(tester, json);
    await pumpHistory(tester, wrapHistory());
    await tester.tap(find.byIcon(Icons.chevron_right).first);
    await tester.pump();
    await tester.tap(find.byIcon(Icons.chevron_left).first);
    await tester.pump();
    expect(find.byType(HistoryScreen), findsOneWidget);
  });

  testWidgets('session tile shows succeeded checkmark', (tester) async {
    final json = jsonEncode({'exercises': []});
    await seedSession(tester, json);
    await pumpHistory(tester, wrapHistory());
    expect(find.byIcon(Icons.check_circle), findsWidgets);
  });

  testWidgets('session tile shows cancel icon on failure', (tester) async {
    final json = jsonEncode({'exercises': []});
    await seedSession(tester, json, duration: 900, succeeded: false);
    await pumpHistory(tester, wrapHistory());
    expect(find.byIcon(Icons.cancel), findsWidgets);
  });

  testWidgets('session duration over 1 hour formats with h prefix', (
    tester,
  ) async {
    final json = jsonEncode({'exercises': []});
    await seedSession(tester, json, duration: 3700);
    await pumpHistory(tester, wrapHistory());
    expect(find.textContaining('1h'), findsOneWidget);
  });
}
