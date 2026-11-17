// The run outlives the screen: nothing but the finish button plus its confirm
// modal ends it. Checks (a) leaving or replacing the screen never stops an
// active run, (b) finishing needs the modal's red check, (c) the app opens on
// the live run.
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_landing.dart';

import '../fake_audio_platform.dart';
import '../run_persist_rig.dart';
import '_run_screen_helpers.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    installFakeAudioPlatform();
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    StorageService.resetForTesting();
    await StorageService.init();
  });

  Future<void> startRun(WidgetTester tester, PersistRig rig) async {
    await tapKey(tester, 'run_start');
    rig.engine.addFix();
    await tester.pumpAndSettle();
  }

  group('(c) the app opens on the run', () {
    testWidgets('coming back to the front lands on the run again', (
      tester,
    ) async {
      final rig = PersistRig();
      RunScreen.defaultControllerFactory = rig.build;
      addTearDown(() => RunScreen.defaultControllerFactory = null);
      await rig.host.cmd('start');
      var owed = false;

      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: RunLanding(
            owed: () async => owed,
            child: const SizedBox(key: Key('home')),
          ),
        ),
      );
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.byType(RunScreen), findsNothing);

      owed = true;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.byType(RunScreen), findsOneWidget);

      // Already on the run: another resume does not stack a second one.
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(RunScreen), findsOneWidget);
    });

    testWidgets('with no run owed home stays home', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: RunLanding(
            owed: () async => false,
            child: const SizedBox(key: Key('home')),
          ),
        ),
      );
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(key('home'), findsOneWidget);
    });
  });
}
