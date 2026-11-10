// The run icon on the home screen opens the run screen.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_audio_platform.dart';
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
    installFakeSecureStorage();
    installFakeAudioPlatform();
  });

  testWidgets('the run icon opens the run screen and back returns home', (
    tester,
  ) async {
    await pumpHome(tester, wrapHome());
    expect(find.byKey(const Key('home_run')), findsOneWidget);

    await tester.tap(find.byKey(const Key('home_run')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byType(RunScreen), findsOneWidget);
    expect(find.byKey(const Key('run_start')), findsOneWidget);

    tester.state<NavigatorState>(find.byType(Navigator)).pop();
    await tester.pumpAndSettle();
    expect(find.byType(RunScreen), findsNothing);
    expect(find.byKey(const Key('home_run')), findsOneWidget);
    // Home reloads on return; let its database reads finish on the real loop.
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
    await tester.pump(const Duration(minutes: 2));
  });
}
