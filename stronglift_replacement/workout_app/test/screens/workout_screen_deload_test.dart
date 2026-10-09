// "Deload now" from an exercise tile mid-workout: the tile re-targets, tapped
// sets keep what was recorded, Finish records the new weight, and every
// refusal (at the floor, storage failing, already finished) says so.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/rep_circle.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

import '../fake_audio_platform.dart';
import '../fake_break_service.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

// Real plan names, seeded as Lunge 7.5 kg x 12 and Row 22.5 kg x 6.
const _lunge = Exercise(name: 'Dumbbell Lunge', sets: 3, reps: 12, weight: 7.5);
const _row = Exercise(name: 'Dumbbell Row', sets: 3, reps: 6, weight: 22.5);
const List<Exercise> _both = [_lunge, _row];

void main() {
  late FakeForegroundBreakClient client;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    installFakeAudioPlatform();
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    client = FakeForegroundBreakClient();
  });

  /// The settings sheet is taller than the default 800x600 test surface.
  void tallScreen(WidgetTester tester) {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }

  Future<void> pumpBoth(WidgetTester tester) {
    tallScreen(tester);
    return pumpWorkout(
      tester,
      wrapWorkout(
        exercises: _both,
        savedState: blankSaved(_both),
        breakClient: client,
      ),
    );
  }

  /// Opens Lunge's settings sheet and taps "Deload now".
  Future<void> openDeload(WidgetTester tester) async {
    await tapReal(
      tester,
      find.bySemanticsLabel('Dumbbell Lunge progression settings'),
    );
    await tester.pump(const Duration(seconds: 1)); // sheet slide-in
    await tapReal(tester, find.text('Deload now'));
  }

  /// Deloads Lunge through the sheet, confirming or cancelling the dialog.
  Future<void> deloadLunge(WidgetTester tester, {bool confirm = true}) async {
    await openDeload(tester);
    expect(find.text('Deload Dumbbell Lunge?'), findsOneWidget);
    await tapReal(tester, find.text(confirm ? 'Deload' : 'Cancel'));
    await tester.pump(const Duration(milliseconds: 300));
  }

  /// Finish -> confirm -> summary dialog up, with the writes done.
  Future<void> finish(WidgetTester tester) async {
    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      await tester.tap(find.widgetWithText(TextButton, 'Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
    });
    await tester.pump(const Duration(milliseconds: 300));
  }

  Future<Map<String, dynamic>> lastSavedWorkout(WidgetTester tester) async {
    final rows = await tester.runAsync(
      () => StorageService.instance.getWorkoutHistory(),
    );
    return jsonDecode(rows!.single['json']! as String) as Map<String, dynamic>;
  }

  testWidgets('re-targets the tile and untapped sets, keeps tapped ones', (
    tester,
  ) async {
    await pumpBoth(tester);
    expect(find.text('3×12×7.5kg'), findsOneWidget);
    final lunge = find.byType(RepCircle).at(0);
    await tapReal(tester, lunge); // set 1: 12 reps, a success -> rest starts
    await tapReal(tester, lunge); // set 1 again: one rep short, 11
    expect(restRunning(tester), isTrue);

    await deloadLunge(tester);

    expect(find.text('3×12×5.0kg'), findsOneWidget);
    expect(find.text('3×12×7.5kg'), findsNothing);
    expect(find.text('3×6×22.5kg'), findsOneWidget);
    final circles = tester.widgetList<RepCircle>(find.byType(RepCircle));
    expect(circles.first.tapped, isTrue);
    expect(circles.first.doneReps, 11);
    expect(circles.elementAt(1).tapped, isFalse);
    expect(circles.elementAt(1).doneReps, 12);
    expect(restRunning(tester), isTrue);

    final stored = await tester.runAsync(
      () => StorageService.instance.getExerciseState(_lunge.name),
    );
    expect(stored!.weight, 5.0);
    final events = await tester.runAsync(
      () => StorageService.instance.getProgressionEvents(exercise: _lunge.name),
    );
    expect(events!.single.source, DeloadSource.workout.storageKey);
    expect(events.single.toWeight, 5.0);
  });

  testWidgets('cancelling the dialog changes nothing', (tester) async {
    await pumpBoth(tester);
    await deloadLunge(tester, confirm: false);
    expect(find.text('3×12×7.5kg'), findsOneWidget);
    final events = await tester.runAsync(
      StorageService.instance.getProgressionEvents,
    );
    expect(events, isEmpty);
  });

  testWidgets('Finish records the deloaded exercise at the new weight', (
    tester,
  ) async {
    await pumpBoth(tester);
    await deloadLunge(tester);
    await tester.tapAt(const Offset(5, 5)); // scrim: close the sheet
    await tester.pump(const Duration(seconds: 1));
    for (var s = 0; s < _both.length * 3; s++) {
      if (restRunning(tester)) await tapReal(tester, find.text('Skip'));
      await tapReal(tester, find.byType(RepCircle).at(s));
    }

    await finish(tester);
    expect(find.byType(WorkoutSummaryDialog), findsOneWidget);

    final saved = await lastSavedWorkout(tester);
    final encoded = jsonEncode((saved['exercises'] as List).first);
    expect(encoded, contains('5.0'));
    expect(encoded, isNot(contains('7.5')));
  });

  testWidgets('refuses at the floor and says so', (tester) async {
    await pumpBoth(tester);
    // Walk the stored target to 0 kg behind the screen's back, so the sheet
    // still offers a deload that storage can no longer give.
    await tester.runAsync(() async {
      ManualDeloadResult r;
      do {
        r = await StorageService.instance.manualDeload(
          _lunge.name,
          source: DeloadSource.settings,
        );
      } while (r.applied);
    });

    await deloadLunge(tester);

    expect(find.textContaining('already at 0 kg'), findsOneWidget);
    expect(find.text('3×12×7.5kg'), findsOneWidget);
  });

  testWidgets('refuses and shows the error when storage throws', (
    tester,
  ) async {
    final dir = Directory.systemTemp.createTempSync('deload_test_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final path = '${dir.path}/workout.db';
    StorageService.resetForTesting(dbPath: path);
    await tester.runAsync(StorageService.init);
    await pumpBoth(tester);
    await tester.runAsync(() async {
      final other = await databaseFactoryFfi.openDatabase(path);
      await other.execute('DROP TABLE exercise_state');
      await other.close();
    });

    await deloadLunge(tester);

    expect(
      find.textContaining('The deload could not be saved'),
      findsOneWidget,
    );
    expect(find.text('3×12×7.5kg'), findsOneWidget);
  });

  testWidgets('refuses once the workout is finished', (tester) async {
    tallScreen(tester);
    await pumpWorkout(
      tester,
      wrapWorkout(
        exercises: _both,
        savedState: completeSaved(),
        breakClient: client,
      ),
    );
    await finish(tester);
    await tester.tap(find.text('Back to Home'));
    await tester.pump(const Duration(milliseconds: 300));

    await deloadLunge(tester);

    expect(find.textContaining('already finished'), findsOneWidget);
    final stored = await tester.runAsync(
      () => StorageService.instance.getExerciseState(_lunge.name),
    );
    expect(stored!.weight, 7.5);
  });

  testWidgets('a screen closed mid-deload still stores the deload', (
    tester,
  ) async {
    await pumpBoth(tester);
    await openDeload(tester);
    await tester.runAsync(() async {
      await tester.tap(find.text('Deload'));
      await Future<void>.delayed(Duration.zero);
      await tester.pumpWidget(const SizedBox());
      await Future<void>.delayed(const Duration(milliseconds: 500));
    });

    final stored = await tester.runAsync(
      () => StorageService.instance.getExerciseState(_lunge.name),
    );
    expect(stored!.weight, 5.0);
  });
}
