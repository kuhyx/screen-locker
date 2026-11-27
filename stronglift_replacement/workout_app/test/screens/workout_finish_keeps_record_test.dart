// Finishing a workout keeps its sync record in the local log before any
// network call: this phone has no sync set up, and the record must still be
// there for the first tick after sign-in.
import 'dart:io';

import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/workout_log_store.dart';

import '../fake_audio_platform.dart';
import '../fake_break_service.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';
import '../icon_finders.dart';

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
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  testWidgets('a finished workout lands in the local log at once', (
    tester,
  ) async {
    await pumpWorkout(
      tester,
      wrapWorkout(
        savedState: completeSaved(),
        breakClient: FakeForegroundBreakClient(),
      ),
    );
    final logFile = File(p.join(workoutLogDirOverride!, kWorkoutLogFileName));
    final text = await tester.runAsync(() async {
      await tester.tap(buttonLabeled<TextButton>('Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      await tester.tap(buttonLabeled<TextButton>('Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
      return logFile.existsSync() ? logFile.readAsString() : null;
    });

    // The record id is the session's start time (see workoutRecordId).
    expect(text, contains('"payload"'));
    expect(text, contains('"workout_type"'));
  });
}
