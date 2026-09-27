// The PER EXERCISE section: each row opens the workout tile's settings sheet,
// edits persist as they happen, and closing the sheet pushes to Firebase.
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

void main() {
  late int pushes;
  late ProgressionSyncResult pushResult;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    pushes = 0;
    pushResult = const ProgressionSyncResult(changed: true, reason: 'pushed');
  });

  Future<void> pumpSettings(WidgetTester tester) async {
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
              return pushResult;
            },
          ),
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.scrollUntilVisible(find.bySemanticsLabel(_situp), 200);
    await tester.pumpAndSettle();
  }

  Future<void> openSitup(WidgetTester tester) async {
    await tester.tap(find.bySemanticsLabel(_situp));
    await tester.pumpAndSettle();
    expect(find.byType(ExerciseSettingsSheet), findsOneWidget);
  }

  /// Dismisses the sheet and lets the push (a real future) complete.
  Future<void> closeSheet(WidgetTester tester) async {
    Navigator.of(tester.element(find.byType(ExerciseSettingsSheet))).pop();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pumpAndSettle();
  }

  Future<ExerciseState> storedSitup(WidgetTester tester) async => (await tester
      .runAsync(() => StorageService.instance.getExerciseState('Situp')))!;

  testWidgets('each row summarises its exercise', (tester) async {
    await pumpSettings(tester);
    // Situp is the one plan exercise without a warmup.
    expect(
      find.text('kg · ↑3 ↓2 · rest 3:00 / 5:00 · no warmup'),
      findsOneWidget,
    );
  });

  testWidgets('a double-progression row names its rep range', (tester) async {
    await tester.runAsync(() async {
      final s = (await StorageService.instance.getExerciseState('Situp'))!;
      await StorageService.instance.setExerciseSettings(
        s.copyWith(
          mode: ProgressionMode.doubleProgression,
          repsHigh: 40,
          repsLow: 25,
        ),
      );
    });
    await pumpSettings(tester);
    expect(find.textContaining('25→40 reps · ↑3 ↓2'), findsOneWidget);
  });

  testWidgets('edits persist, show on the row, and push once on close', (
    tester,
  ) async {
    await pumpSettings(tester);
    await openSitup(tester);
    await tester.runAsync(() async {
      await tester.tap(find.bySemanticsLabel('Success rest up'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();
    await tester.tap(find.text('Reps'));
    await tester.pump();
    await tester.tap(find.text('Pause'));
    await tester.pump();
    await closeSheet(tester);

    expect(pushes, 1);
    final s = await storedSitup(tester);
    expect(s.restSuccessSecs, 195);
    expect(s.mode, ProgressionMode.reps);
    expect(s.pausedUntil, isNotNull);
    expect(find.textContaining('reps · ↑3 ↓2 · rest 3:15 / 5:00'), findsOne);
    expect(find.textContaining('Paused — back on'), findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);
  });

  testWidgets('closing without an edit pushes nothing', (tester) async {
    await pumpSettings(tester);
    await openSitup(tester);
    await closeSheet(tester);
    expect(pushes, 0);
  });

  testWidgets('a push that did not happen says so', (tester) async {
    pushResult = const ProgressionSyncResult(
      changed: false,
      reason: 'no Firebase account on this device',
    );
    await pumpSettings(tester);
    await openSitup(tester);
    await tester.tap(find.bySemanticsLabel('Fail rest down'));
    await tester.pump();
    await closeSheet(tester);

    expect(pushes, 1);
    expect(
      find.text(
        'Saved on this phone, not synced: no Firebase account on this device',
      ),
      findsOneWidget,
    );
  });
}
