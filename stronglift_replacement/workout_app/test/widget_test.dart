import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/main.dart';
import 'package:workout_app/services/http_server_service.dart';
import 'package:workout_app/services/storage_service.dart';

import 'fake_secure_storage.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    // These tests build the whole WorkoutApp, so they cannot inject a sync
    // probe the way home_screen_test does. The home screen now syncs in the
    // background on open, which reaches FlutterSecureStorage -- whose real
    // platform channel throws under `flutter test`. Install the fake instead
    // of letting an unrelated MissingPluginException fail these.
    installFakeSecureStorage();
    StorageService.resetForTesting();
    await StorageService.init();
  });

  testWidgets('WorkoutApp renders HomeScreen', (tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(const WorkoutApp());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
    expect(find.text('Workout Tracker'), findsOneWidget);
  });

  testWidgets('app-lifecycle changes drive the HTTP server', (tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(const WorkoutApp());
      await Future<void>.delayed(const Duration(milliseconds: 100));
      // A valid forward transition path that visits every handled state.
      for (final state in const [
        AppLifecycleState.resumed,
        AppLifecycleState.inactive,
        AppLifecycleState.hidden,
        AppLifecycleState.paused,
        AppLifecycleState.detached,
      ]) {
        tester.binding.handleAppLifecycleStateChanged(state);
        await Future<void>.delayed(const Duration(milliseconds: 5));
      }
      await HttpServerService.instance.stop();
    });
    await tester.pump();
  });
}
