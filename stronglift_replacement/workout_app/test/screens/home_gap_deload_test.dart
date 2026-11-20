// The gap deload end to end on launch: home cuts the lift before it reads
// the targets, and the auto-opened workout shows the old weight struck
// through next to the new one.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/screens/workout_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_audio_platform.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeAudioPlatform();
  });

  testWidgets('an 8-day gap opens the workout one step lighter', (
    tester,
  ) async {
    final lift = workoutA.first.name;
    final end = DateTime.now().subtract(const Duration(days: 8));
    await tester.runAsync(() async {
      final svc = StorageService.instance;
      await svc.setExerciseWeight(lift, 25);
      await svc.saveSession(
        date: end.toIso8601String().substring(0, 10),
        // B last, so the next workout is A and holds the lift.
        workoutType: 'B',
        durationSeconds: 3600,
        succeeded: true,
        json: jsonEncode({
          'end_time': end.toIso8601String(),
          'exercises': [
            {'name': lift, 'targetWeight': 25, 'targetReps': 5},
          ],
        }),
      );
    });

    await tester.runAsync(() async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: HomeScreen(configuredProbe: () async => false),
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump(); // fire the post-frame auto-open
      await Future<void>.delayed(const Duration(milliseconds: 500));
    });
    await tester.pump();
    // The workout's own load (targets, then the deload marks) on the real
    // loop too.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 500)),
    );
    await tester.pump();

    expect(find.byType(WorkoutScreen), findsOneWidget);
    final s = await tester.runAsync(
      () => StorageService.instance.getExerciseState(lift),
    );
    expect(s!.weight, 22.5);
    expect(find.byIcon(Icons.arrow_downward), findsOneWidget);
  });
}
