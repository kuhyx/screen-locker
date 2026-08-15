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

  testWidgets('shows Workout Tracker app bar', (tester) async {
    await pumpHome(tester, wrapHome());
    expect(find.text('Workout Tracker'), findsOneWidget);
  });

  testWidgets('shows Next: Workout A when no workout done', (tester) async {
    await pumpHome(tester, wrapHome());
    expect(find.textContaining('Next: Workout A'), findsOneWidget);
  });

  testWidgets('shows Start Workout A button', (tester) async {
    await pumpHome(tester, wrapHome());
    expect(find.text('Start Workout A'), findsOneWidget);
  });

  testWidgets('history icon navigates to history screen', (tester) async {
    await pumpHome(tester, wrapHome());
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Progress'), findsOneWidget);
  });

  testWidgets('settings icon navigates to settings screen', (tester) async {
    await pumpHome(tester, wrapHome());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('"Done for today" message shows after saving a session today', (
    tester,
  ) async {
    final today = DateTime.now();
    final dateStr =
        '${today.year}-${today.month.toString().padLeft(2, '0')}'
        '-${today.day.toString().padLeft(2, '0')}';
    // DB writes need the real event loop (the widget-test zone fakes async and
    // would hang sqflite-ffi); run the seed inside runAsync.
    await tester.runAsync(
      () => StorageService.instance.saveSession(
        date: dateStr,
        workoutType: 'A',
        durationSeconds: 1800,
        succeeded: true,
        json: '{"exercises":[]}',
      ),
    );
    await pumpHome(tester, wrapHome());
    expect(find.text('Done for today!'), findsOneWidget);
  });

  testWidgets('manual-workout icon navigates to the manual form', (
    tester,
  ) async {
    installFakeSecureStorage(); // ManualWorkoutScreen loads its sync budget
    await pumpHome(tester, wrapHome());
    await tester.tap(find.byIcon(Icons.edit_note));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Log Manual Workout'), findsOneWidget);
  });

  testWidgets('starting a workout navigates to the workout screen', (
    tester,
  ) async {
    await pumpHome(tester, wrapHome());
    await tester.tap(find.text('Start Workout A'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('Workout A'), findsWidgets);
  });

  testWidgets('an active session auto-resumes into the workout screen', (
    tester,
  ) async {
    await tester.runAsync(
      () => StorageService.instance.saveActiveSession({
        'workoutType': 'A',
        'startTime': DateTime.now().toIso8601String(),
        'exercises': <dynamic>[],
      }),
    );
    await pumpHome(tester, wrapHome());
    await tester.pump(const Duration(milliseconds: 300));
    // The post-frame auto-resume pushed the workout screen.
    expect(find.textContaining('Workout A'), findsWidgets);
  });

  testWidgets('active session shows Resume, returns (98) and re-enters (153)', (
    tester,
  ) async {
    // A fully-formed active session so WorkoutScreen restores cleanly (its
    // _restoreFromSaved expects startTimeMs + per-exercise tapped/doneReps).
    await tester.runAsync(
      () => StorageService.instance.saveActiveSession({
        'workoutType': 'A',
        'startTimeMs': DateTime.now().millisecondsSinceEpoch,
        'tapped': [for (final e in workoutA) List<bool>.filled(e.sets, false)],
        'doneReps': [
          for (final e in workoutA) List<int>.filled(e.sets, e.reps),
        ],
        'warmupTapped': List<bool>.filled(workoutA.length, false),
      }),
    );
    // Drive the whole first-load + post-frame auto-resume push on the real loop
    // (auto-resume awaits getCurrentExercises, which hangs under FakeAsync).
    await tester.runAsync(() async {
      await tester.pumpWidget(wrapHome());
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump(); // fire the post-frame auto-resume callback
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(WorkoutScreen), findsOneWidget);

    // Return to home; auto-resume is now consumed so the Resume button shows.
    await tester.runAsync(() async {
      tester.state<NavigatorState>(find.byType(Navigator).last).pop();
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(WorkoutScreen), findsNothing);
    expect(find.text('Resume Workout'), findsOneWidget);

    // Tapping Resume invokes onResume -> _openWorkout(resume:true) (line 153).
    await tester.runAsync(() async {
      await tester.tap(find.text('Resume Workout'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(WorkoutScreen), findsOneWidget);
  });

  testWidgets('returning from settings reloads the home screen', (
    tester,
  ) async {
    installFakeSecureStorage(); // SettingsScreen reads the sync token on init
    await pumpHome(tester, wrapHome());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Settings'), findsOneWidget);

    // Pop back; the trailing _load() (line 135) needs the real loop for DB I/O.
    await tester.runAsync(() async {
      tester.state<NavigatorState>(find.byType(Navigator).last).pop();
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Workout Tracker'), findsOneWidget);
  });
}
