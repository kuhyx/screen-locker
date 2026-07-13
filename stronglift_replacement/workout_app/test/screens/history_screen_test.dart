import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/history_screen.dart';
import 'package:workout_app/services/storage_service.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
  });

  Future<void> _pump(WidgetTester tester, Widget w) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(w);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
  }

  Widget _wrap() => const MaterialApp(home: HistoryScreen());

  // Seed a workout. DB writes must run on the real event loop: the widget-test
  // zone fakes async, so a sqflite-ffi write in the test body hangs (then the
  // isolate crashes on shutdown). runAsync gives the write the real loop.
  Future<void> _seed(
    WidgetTester tester,
    String json, {
    String date = '2024-06-01',
    String type = 'A',
    int duration = 1800,
    bool succeeded = true,
  }) async {
    await tester.runAsync(
      () => StorageService.instance.saveSession(
        date: date,
        workoutType: type,
        durationSeconds: duration,
        succeeded: succeeded,
        json: json,
      ),
    );
  }

  testWidgets('shows Progress app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Progress'), findsOneWidget);
  });

  testWidgets('shows "No workouts yet." when history is empty', (tester) async {
    await _pump(tester, _wrap());
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
    await _seed(tester, json);
    await _pump(tester, _wrap());
    expect(find.textContaining('Workout A'), findsWidgets);
  });

  testWidgets('exercise picker shows "Total (all workouts)" initially',
      (tester) async {
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
    await _seed(tester, json);
    await _pump(tester, _wrap());
    expect(find.textContaining('Total'), findsOneWidget);
  });

  testWidgets('calendar prev/next month navigation works', (tester) async {
    final json = jsonEncode({'exercises': []});
    await _seed(tester, json);
    await _pump(tester, _wrap());
    await tester.tap(find.byIcon(Icons.chevron_right).first);
    await tester.pump();
    await tester.tap(find.byIcon(Icons.chevron_left).first);
    await tester.pump();
    expect(find.byType(HistoryScreen), findsOneWidget);
  });

  testWidgets('session tile shows succeeded checkmark', (tester) async {
    final json = jsonEncode({'exercises': []});
    await _seed(tester, json);
    await _pump(tester, _wrap());
    expect(find.byIcon(Icons.check_circle), findsWidgets);
  });

  testWidgets('session tile shows cancel icon on failure', (tester) async {
    final json = jsonEncode({'exercises': []});
    await _seed(tester, json, duration: 900, succeeded: false);
    await _pump(tester, _wrap());
    expect(find.byIcon(Icons.cancel), findsWidgets);
  });

  testWidgets('session duration over 1 hour formats with h prefix',
      (tester) async {
    final json = jsonEncode({'exercises': []});
    await _seed(tester, json, duration: 3700);
    await _pump(tester, _wrap());
    expect(find.textContaining('1h'), findsOneWidget);
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
      await _seed(tester, json, date: '2024-06-0$i');
    }
    await _pump(tester, _wrap());
    expect(find.byType(HistoryScreen), findsOneWidget);
  });
}
