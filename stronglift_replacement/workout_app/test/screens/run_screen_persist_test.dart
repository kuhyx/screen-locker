// The run outlives the screen: nothing but the finish button plus its confirm
// modal ends it. Checks (a) leaving or replacing the screen never stops an
// active run, (b) finishing needs the modal's red check, (c) the app opens on
// the live run.
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/widgets/run_landing.dart';

import '../fake_audio_platform.dart';
import '../run_persist_rig.dart';
import '_run_screen_helpers.dart';

void main() {
  setUp(installFakeAudioPlatform);

  Future<void> startRun(WidgetTester tester, PersistRig rig) async {
    await tapKey(tester, 'run_start');
    rig.engine.addFix();
    await tester.pumpAndSettle();
  }

  group('(a) the run outlives the screen', () {
    testWidgets('disposing the screen leaves the run recording', (
      tester,
    ) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);
      final engine = rig.engine;

      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();

      expect(find.byType(RunScreen), findsNothing);
      expect(engine.phase, RunPhase.recording);
      expect(engine.disposed, isFalse);
      expect(rig.service.calls, isNot(contains('stop')));
      expect(rig.host.saved, isEmpty);
    });

    testWidgets('back and pop do nothing while recording or paused', (
      tester,
    ) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(RunScreen), findsOneWidget);

      await tapKey(tester, 'run_pause');
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(RunScreen), findsOneWidget);
      expect(rig.engine.phase, RunPhase.paused);
      expect(rig.service.calls, isNot(contains('stop')));
    });

    testWidgets('a second screen finds the run and cannot restart it', (
      tester,
    ) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);
      final engine = rig.engine;

      // The system closed the screen; the app opens a new one.
      await tester.pumpWidget(const SizedBox());
      await rig.pump(tester, resuming: true);

      expect(key('run_pause'), findsOneWidget, reason: 'live run, not idle');
      expect(key('run_start'), findsNothing);
      // A start command from the new controller is refused by the host.
      await rig.controllers.last.start();
      expect(rig.host.engines, hasLength(1));
      expect(engine.starts, 1);
      expect(engine.phase, RunPhase.recording);
      expect(rig.service.calls, isNot(contains('stop')));
    });

    testWidgets('"new run" cannot replace a run that is still going', (
      tester,
    ) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);
      final engine = rig.engine;

      // A rebuilt controller (what "new run" makes) asking to start.
      final second = rig.build();
      await second.attach();
      await second.start();

      expect(rig.host.engines, hasLength(1));
      expect(engine.phase, RunPhase.recording);
      expect(engine.disposed, isFalse);
      second.dispose();
    });
  });

  group('(b) finishing needs the modal', () {
    testWidgets('the finish button asks, the cross keeps recording', (
      tester,
    ) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);

      await tapKey(tester, 'run_finish');
      expect(key('run_finish_dialog'), findsOneWidget);
      expect(rig.engine.phase, RunPhase.recording);

      await tapKey(tester, 'run_finish_cancel');
      expect(key('run_finish_dialog'), findsNothing);
      expect(rig.engine.phase, RunPhase.recording);
      expect(rig.host.saved, isEmpty);
      expect(key('run_pause'), findsOneWidget);
    });

    testWidgets('tapping outside or pressing back cancels', (tester) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);

      await tapKey(tester, 'run_finish');
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(key('run_finish_dialog'), findsNothing);
      expect(rig.engine.phase, RunPhase.recording);

      await tapKey(tester, 'run_finish');
      await tester.tapAt(const Offset(2, 2));
      await tester.pumpAndSettle();
      expect(key('run_finish_dialog'), findsNothing);
      expect(rig.engine.phase, RunPhase.recording);
    });

    testWidgets('the red check ends and saves the run', (tester) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);

      await tapKey(tester, 'run_finish');
      await tapKey(tester, 'run_finish_confirm');
      await tester.pumpAndSettle();

      expect(rig.engine.phase, RunPhase.finished);
      expect(rig.host.saved, hasLength(1));
      expect(key('run_saved_ok'), findsOneWidget);
      expect(rig.service.calls.last, 'stop');
      expect(key('run_again'), findsOneWidget);
    });

    testWidgets('the modal shows icons only, no words', (tester) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);
      await tapKey(tester, 'run_finish');

      final dialog = find.byKey(const Key('run_finish_dialog'));
      expect(
        find.descendant(of: dialog, matching: find.byType(Text)),
        findsNothing,
      );
      expect(
        find.descendant(of: dialog, matching: find.byIcon(Icons.check)),
        findsOneWidget,
      );
      expect(
        find.descendant(of: dialog, matching: find.byIcon(Icons.close)),
        findsOneWidget,
      );
    });

    testWidgets('advice makes the finish button pulse, nothing more', (
      tester,
    ) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);
      expect(key('run_finish_still'), findsOneWidget);

      rig.host.lastHooks.onSuggest('stationary');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(key('run_finish_pulse'), findsOneWidget);
      expect(rig.engine.phase, RunPhase.recording);
      expect(key('run_finish_dialog'), findsNothing);
      expect(rig.host.saved, isEmpty);
    });

    testWidgets('a notification tap on advice opens the modal, still unconfirmed', (
      tester,
    ) async {
      final rig = PersistRig();
      await rig.pump(tester);
      await startRun(tester, rig);
      rig.host.lastHooks.onSuggest('gpsLost');
      await tester.pump();

      rig.host.host.notificationPressed();
      await tester.pump();
      await tester.pump();

      expect(key('run_finish_dialog'), findsOneWidget);
      expect(rig.engine.phase, RunPhase.recording);

      await tapKey(tester, 'run_finish_cancel');
      expect(rig.engine.phase, RunPhase.recording);
      expect(key('run_finish_dialog'), findsNothing);
    });
  });

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
