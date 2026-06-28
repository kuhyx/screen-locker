import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/settings_screen.dart';
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

  Widget _wrap() => const MaterialApp(home: SettingsScreen());

  testWidgets('shows Settings app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('shows WEIGHTS and PROGRESSION THRESHOLDS sections',
      (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('WEIGHTS'), findsOneWidget);
    expect(find.text('PROGRESSION THRESHOLDS'), findsOneWidget);
  });

  testWidgets('shows all exercise names from both workout plans', (tester) async {
    await _pump(tester, _wrap());
    for (final ex in [...workoutA, ...workoutB]) {
      expect(find.text(ex.name), findsWidgets);
    }
  });

  testWidgets('Reset defaults button is present', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Reset defaults'), findsOneWidget);
  });

  testWidgets('increment weight button increases weight', (tester) async {
    await _pump(tester, _wrap());

    final firstName = workoutA.first.name;
    final state = await StorageService.instance.getExerciseState(firstName);
    final before = state!.weight;

    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pump();

    expect(find.textContaining('${before + kWeightIncrement}kg'), findsWidgets);
  });

  testWidgets('decrement weight button decreases weight', (tester) async {
    await _pump(tester, _wrap());

    final firstName = workoutA.first.name;
    final state = await StorageService.instance.getExerciseState(firstName);
    final before = state!.weight;

    await tester.tap(find.byIcon(Icons.remove).first);
    await tester.pump();

    expect(
      find.textContaining('${before - kWeightIncrement}kg'),
      findsWidgets,
    );
  });

  testWidgets('threshold circles show values 1-5', (tester) async {
    await _pump(tester, _wrap());
    for (int i = 1; i <= 5; i++) {
      expect(find.text('$i'), findsWidgets);
    }
  });

  testWidgets('Reset dialog shows on tap and cancels', (tester) async {
    await _pump(tester, _wrap());
    await tester.tap(find.text('Reset defaults'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Reset to defaults?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    expect(find.text('Reset to defaults?'), findsNothing);
  });

  testWidgets('Reset dialog confirms and resets data', (tester) async {
    await StorageService.instance
        .setExerciseWeight(workoutA.first.name, 99.0);

    await _pump(tester, _wrap());
    await tester.tap(find.text('Reset defaults'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Reset'));
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final state =
        await StorageService.instance.getExerciseState(workoutA.first.name);
    expect(state!.weight, workoutA.first.weight);
  });
}
