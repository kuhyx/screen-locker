// Manual deload from the Settings screen's exercise sheet: the stored and
// shown weights move, a refusal is spoken, a pending stepper write cannot
// undo it, and the progression push fires when the sheet closes.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/exercise_settings_sheet.dart';

import '../fake_secure_storage.dart';

const _situp = 'Situp exercise settings';
const _lunge = 'Dumbbell Lunge exercise settings';

void main() {
  late int pushes;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    pushes = 0;
  });

  Future<void> pumpSettings(WidgetTester tester) async {
    // Tall enough that no scrolling (which advances the fake clock) is needed
    // between a stepper tap and the deload: the debounce is 600 ms.
    tester.view
      ..physicalSize = const Size(800, 3000)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.runAsync(() async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: SettingsScreen(
            firebaseFactory: () async => null,
            accountLoader: () async => null,
            sessionProbe: () async => false,
            storageChecker: () async => false,
            progressionPuller: () async =>
                const ProgressionSyncResult(changed: false, reason: 'stub'),
            progressionPusher: () async {
              pushes++;
              return const ProgressionSyncResult(
                changed: true,
                reason: 'pushed',
              );
            },
          ),
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
  }

  Future<void> openExercise(WidgetTester tester, String label) async {
    await tester.tap(find.bySemanticsLabel(label));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(ExerciseSettingsSheet), findsOneWidget);
  }

  /// Taps "Deload now" and confirms; the storage write is a real future.
  Future<void> deloadNow(WidgetTester tester) async {
    await tester.tap(find.text('Deload now'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await tester.tap(find.widgetWithText(TextButton, 'Deload'));
    await tester.pump();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pumpAndSettle();
  }

  Future<void> closeSheet(WidgetTester tester) async {
    Navigator.of(tester.element(find.byType(ExerciseSettingsSheet))).pop();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pumpAndSettle();
  }

  /// The weight shown on the WEIGHTS row of the first lunge.
  Future<String> lungeWeight(WidgetTester tester) async {
    final row = find
        .ancestor(
          of: find.text('Dumbbell Lunge').first,
          matching: find.byType(Row),
        )
        .first;
    return tester
        .widget<Text>(
          find.descendant(of: row, matching: find.textContaining('kg')),
        )
        .data!;
  }

  Future<ExerciseState> stored(WidgetTester tester, String name) async =>
      (await tester.runAsync(
        () => StorageService.instance.getExerciseState(name),
      ))!;

  testWidgets('deloading updates the list, the store and pushes on close', (
    tester,
  ) async {
    await pumpSettings(tester);
    expect(await lungeWeight(tester), '7.5kg');
    await openExercise(tester, _lunge);
    await deloadNow(tester);

    expect(find.text('Deload  5 kg × 12 → 2.5 kg'), findsOneWidget);
    expect((await stored(tester, 'Dumbbell Lunge')).weight, 5);
    expect(pushes, 0);

    await closeSheet(tester);
    expect(pushes, 1);
    expect(await lungeWeight(tester), '5.0kg');
  });

  testWidgets('a refused deload shows why and pushes nothing', (tester) async {
    await pumpSettings(tester);
    await openExercise(tester, _situp);
    // The sheet still offers a step down, but the store is already at 0 kg.
    await tester.runAsync(
      () => StorageService.instance.setExerciseWeight('Situp', 0),
    );
    await deloadNow(tester);

    expect(find.textContaining('Situp is already at 0 kg × 30'), findsOne);
    expect(find.text('Deload  10 kg × 30 → 7.5 kg'), findsOneWidget);
    await closeSheet(tester);
    expect(pushes, 0);
  });

  testWidgets('a pending stepper write cannot undo the deload', (tester) async {
    await pumpSettings(tester);
    // First weight row is the lunge; this queues a 600 ms debounced write
    // of 10 kg.
    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pump();
    expect(await lungeWeight(tester), '10.0kg');
    await openExercise(tester, _lunge);
    await deloadNow(tester);

    await tester.pump(const Duration(milliseconds: 700));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump();
    expect((await stored(tester, 'Dumbbell Lunge')).weight, 5);
    await closeSheet(tester);
    expect(await lungeWeight(tester), '5.0kg');
  });
}
