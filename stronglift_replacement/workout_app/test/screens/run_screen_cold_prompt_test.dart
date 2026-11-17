// A notification tap on standing advice that lands while no screen is
// listening (a cold start: the UI process was dead) still opens the finish
// modal once the screen attaches and asks the host where the run stands.
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';

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

  testWidgets('a press before the screen exists shows the modal on attach', (
    tester,
  ) async {
    final rig = PersistRig();
    await rig.host.cmd('start');
    rig.host.lastHooks.onSuggest('gpsRestored');
    // The plugin reaches the service while the UI process is still starting.
    rig.host.host.notificationPressed();

    // Not rig.pump: its pumpAndSettle never ends while the pulse repeats.
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: rig.navigator,
        theme: buildAppTheme(),
        home: const SizedBox(),
      ),
    );
    rig.navigator.currentState!.push(
      MaterialPageRoute<void>(builder: (_) => rig.screen(resuming: true)),
    );
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(key('run_finish_dialog'), findsOneWidget);
    expect(rig.engine.phase, RunPhase.recording);
    expect(key('run_finish_pulse'), findsOneWidget);

    await tester.tap(key('run_finish_cancel'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(rig.engine.phase, RunPhase.recording);
    expect(key('run_finish_dialog'), findsNothing);
  });
}
