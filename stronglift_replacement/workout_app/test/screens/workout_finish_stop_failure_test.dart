// Finishing a workout whose break service will not stop: the summary still
// appears (the stop no longer gates it) and the failure is logged, not thrown.
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

/// A client whose teardown fails once [failStop] is armed.
class _FailingStopClient extends FakeForegroundBreakClient {
  bool failStop = false;

  @override
  void stopListeningForDrainNudges() {
    if (failStop) {
      failStop = false;
      throw StateError('notification teardown failed');
    }
    super.stopListeningForDrainNudges();
  }
}

void main() {
  late _FailingStopClient client;

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
    client = _FailingStopClient();
  });

  testWidgets('a failed service stop still shows the summary', (tester) async {
    await pumpWorkout(
      tester,
      wrapWorkout(savedState: completeSaved(), breakClient: client),
    );
    client.failStop = true;
    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      await tester.tap(find.widgetWithText(TextButton, 'Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
    });
    await tester.pump();

    expect(client.failStop, isFalse, reason: 'the failing stop really ran');
    expect(tester.takeException(), isNull);
    // The summary's PC line: this test host is never paired.
    expect(
      find.text('PC: will credit within 60 s (via sync)'),
      findsOneWidget,
    );
  });
}
