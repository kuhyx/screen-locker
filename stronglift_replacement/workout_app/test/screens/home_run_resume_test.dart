// (c) A run in progress opens the app on the live run screen.
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/home_screen.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_audio_platform.dart';
import '../fake_secure_storage.dart';
import '../run_persist_rig.dart';
import '_home_test_fixtures.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    installFakeAudioPlatform();
  });

  Widget app({required bool openRun, bool openWorkout = false}) => MaterialApp(
    theme: buildAppTheme(),
    home: HomeScreen(
      configuredProbe: () async => false,
      clock: () => DateTime(2026, 8, 15, 18),
      openWorkoutOnLaunch: openWorkout,
      openRunOnLaunch: openRun,
    ),
  );

  testWidgets('a cold start with a run owed lands on the run screen', (
    tester,
  ) async {
    final rig = PersistRig();
    RunScreen.defaultControllerFactory = rig.build;
    addTearDown(() => RunScreen.defaultControllerFactory = null);
    await rig.host.cmd('start'); // the host restored the run
    rig.engine.addFix();

    await pumpHome(tester, app(openRun: true, openWorkout: true));
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.byType(RunScreen), findsOneWidget);
    expect(find.byKey(const Key('run_pause')), findsOneWidget);
    expect(find.byKey(const Key('run_start')), findsNothing);
    // The workout did not open over it, and back does nothing.
    await tester.binding.handlePopRoute();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byType(RunScreen), findsOneWidget);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 300)),
    );
  });

  testWidgets('with no run owed home shows as before', (tester) async {
    await pumpHome(tester, app(openRun: false));
    expect(find.byType(RunScreen), findsNothing);
    expect(find.byKey(const Key('home_run')), findsOneWidget);
  });
}
