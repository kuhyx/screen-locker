// textgate guard: the main screens paint no chrome words.
//
// Each test pumps one screen through the same fixtures its own test file
// uses and asserts, via [expectTextFree], that nothing painted holds a word
// besides exercise names and unit symbols after numbers.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/screens/manual_workout_screen.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

import 'fake_audio_platform.dart';
import 'fake_pc_pairing.dart';
import 'fake_secure_storage.dart';
import 'screens/_history_test_fixtures.dart';
import 'screens/_home_test_fixtures.dart';
import 'screens/_manual_screen_fixtures.dart';
import 'screens/_workout_screen_test_fixtures.dart';
import 'text_free_guard.dart';

String _sessionJson() => jsonEncode({
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

WorkoutSession _session({required bool ok}) {
  final start = DateTime(2024, 6, 1, 9);
  return WorkoutSession(
    workoutType: 'A',
    startTime: start,
    endTime: start.add(const Duration(minutes: 45)),
    exercises: [
      ExerciseResult(
        exercise: const Exercise(name: 'Squat', sets: 3, reps: 5, weight: 20),
        sets: List.generate(
          3,
          (_) => SetResult(targetReps: 5, doneReps: ok ? 5 : 3, weight: 20),
        ),
      ),
    ],
  );
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    installFakeAudioPlatform();
  });

  testWidgets('home, nothing done yet', (tester) async {
    await pumpHome(tester, wrapHome());
    expectTextFree(tester);
  });

  testWidgets('home, done for today', (tester) async {
    await seedSession(tester, _sessionJson(), date: '2026-08-15');
    await pumpHome(tester, wrapHome());
    expectTextFree(tester);
  });

  testWidgets('workout screen', (tester) async {
    await pumpWorkout(tester, wrapWorkout());
    expectTextFree(tester);
  });

  testWidgets('history, empty and with a session', (tester) async {
    await pumpHistory(tester, wrapHistory());
    expectTextFree(tester);
    await seedSession(tester, _sessionJson());
    await pumpHistory(tester, wrapHistory());
    expectTextFree(tester);
  });

  testWidgets('settings', (tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: SettingsScreen(
            pcPairingLoader: fakePcPairing,
            firebaseFactory: () async => null,
            accountLoader: () async => null,
            sessionProbe: () async => false,
            storageChecker: () async => false,
            progressionPuller: () async =>
                const ProgressionSyncResult(changed: false, reason: 'stub'),
          ),
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    expectTextFree(tester);
  });

  testWidgets('manual workout form', (tester) async {
    await pumpManual(
      tester,
      ManualWorkoutScreen(syncService: FakeManualSync(), clock: fixedManualNow),
    );
    expectTextFree(tester);
  });

  for (final ok in [true, false]) {
    testWidgets('summary dialog, all succeeded: $ok', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: WorkoutSummaryDialog(
            session: _session(ok: ok),
            syncResult: const SyncResult(success: true, path: '/sdcard/x.json'),
          ),
        ),
      );
      expectTextFree(tester);
    });
  }
}
