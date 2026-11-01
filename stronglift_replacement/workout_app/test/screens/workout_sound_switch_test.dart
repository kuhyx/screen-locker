// The sound switch reaches every sound: the break-end cue on screen, and the
// foreground service that rings it when the screen is off.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_audio_platform.dart';
import '../fake_break_service.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

void main() {
  late FakeAudioRecorder audio;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    audio = installFakeAudioPlatform();
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  Future<void> setSound(WidgetTester tester, {required bool enabled}) => tester
      .runAsync(() => StorageService.instance.setSoundEnabled(enabled: enabled))
      .then((_) {});

  group('the sound switch also governs the break-end cue', () {
    testWidgets('on: an overdue rest still rings', (tester) async {
      await pumpWorkout(tester, wrapWorkout(savedState: savedWithBreak(-45)));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 300)),
      );
      await tester.pump();
      expect(audio.resumedSources.where((s) => s.contains('break_end')), [
        isNotNull,
      ]);
    });

    testWidgets('off: the same rest is silent', (tester) async {
      await setSound(tester, enabled: false);
      await pumpWorkout(tester, wrapWorkout(savedState: savedWithBreak(-45)));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 300)),
      );
      await tester.pump();
      expect(audio.resumedSources, isEmpty);
    });
  });

  group('the notification service is told the choice', () {
    Future<bool> pushedSound(WidgetTester tester, {required bool on}) async {
      await setSound(tester, enabled: on);
      final client = FakeForegroundBreakClient();
      await pumpWorkout(
        tester,
        wrapWorkout(savedState: blankSaved(), breakClient: client),
      );
      return client.pushed.last.soundOn;
    }

    testWidgets('on', (tester) async {
      expect(await pushedSound(tester, on: true), isTrue);
    });

    testWidgets('off', (tester) async {
      expect(await pushedSound(tester, on: false), isFalse);
    });
  });
}
