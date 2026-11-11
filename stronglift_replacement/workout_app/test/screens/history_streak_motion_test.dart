// The streak card counts to its real values on arrival instead of snapping.
// The numbers themselves are untouched: only the road to them is animated.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/services/storage_service.dart';

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
    installFakeSecureStorage();
  });

  Future<void> openExercise(WidgetTester tester, String name) async {
    final json = jsonEncode({
      'exercises': [
        {
          'name': name,
          'targetSets': 3,
          'targetReps': 5,
          'targetWeight': 20.0,
          'warmupDone': false,
          'succeeded': true,
          'sets': <Map<String, dynamic>>[],
        },
      ],
    });
    await seedSession(tester, json, date: '2024-06-01');
    await pumpHistory(tester, wrapHistory());
    await tester.runAsync(() async {
      await tester.tap(find.byType(DropdownButton<String>));
      await Future<void>.delayed(const Duration(milliseconds: 400));
      await tester.pump();
      await tester.tap(find.text(name).last);
      await Future<void>.delayed(const Duration(milliseconds: 400));
      await tester.pump();
    });
  }

  testWidgets('the success streak counts up to its true value', (tester) async {
    final name = workoutA.first.name;
    final seeded = (await tester.runAsync(
      () => StorageService.instance.getExerciseState(name),
    ))!;
    await tester.runAsync(
      () => StorageService.instance.replaceExerciseState(
        seeded.copyWith(successStreak: 2, failStreak: 0),
      ),
    );
    final threshold = seeded.successThreshold;
    final upRow = find.textContaining(RegExp(r'^\d+  ↑'));

    await openExercise(tester, name);
    await tester.pump();
    expect(
      tester.widget<Text>(upRow).data,
      startsWith('$threshold  ↑'),
      reason: 'first frame: nothing counted yet, every dot still to fill',
    );

    await tester.pumpAndSettle();
    expect(
      tester.widget<Text>(upRow).data,
      startsWith('${threshold - 2}  ↑'),
      reason: 'settled: exactly the stored streak, never an invented one',
    );
  });

  testWidgets('a streak of zero is shown at once, with no motion', (
    tester,
  ) async {
    final name = workoutA.first.name;
    final seeded = (await tester.runAsync(
      () => StorageService.instance.getExerciseState(name),
    ))!;
    await openExercise(tester, name);
    await tester.pump();
    expect(
      tester.widget<Text>(find.textContaining(RegExp(r'^\d+  ↑'))).data,
      startsWith('${seeded.successThreshold}  ↑'),
    );
  });
}
