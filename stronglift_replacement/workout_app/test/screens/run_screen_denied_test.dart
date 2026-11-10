// Location refused: no map, no start, only the red icon; a grant later (the
// app coming back from settings) brings the screen back.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/widgets/run_map.dart';

import '../fake_audio_platform.dart';
import '_run_screen_fixtures.dart';

void _background(WidgetTester tester) {
  for (final state in [
    AppLifecycleState.inactive,
    AppLifecycleState.hidden,
    AppLifecycleState.paused,
  ]) {
    tester.binding.handleAppLifecycleStateChanged(state);
  }
}

Future<void> _resume(WidgetTester tester) async {
  _background(tester);
  for (final state in [
    AppLifecycleState.hidden,
    AppLifecycleState.inactive,
    AppLifecycleState.resumed,
  ]) {
    tester.binding.handleAppLifecycleStateChanged(state);
  }
  await tester.pumpAndSettle();
}

const _refusals = [
  (LocationAccess.denied, 'run_issue_denied'),
  (LocationAccess.deniedForever, 'run_issue_deniedForever'),
  (LocationAccess.serviceOff, 'run_issue_serviceOff'),
];

void main() {
  setUp(installFakeAudioPlatform);

  for (final (access, id) in _refusals) {
    testWidgets('${access.name}: no map, no start, just the red icon', (
      tester,
    ) async {
      final h = RunHarness(access: access);
      await h.pump(tester);

      expect(find.byType(RunMap), findsNothing);
      expect(key('run_map_slot'), findsNothing);
      expect(key('run_start'), findsNothing);
      expect(key('run_pace_toggle'), findsNothing);
      expect(key(id), findsOneWidget);
      expect(find.byIcon(Icons.location_disabled), findsOneWidget);
      expect(h.service.calls, isEmpty);
    });
  }

  testWidgets('denied once: the icon asks again and can recover', (
    tester,
  ) async {
    final h = RunHarness(access: LocationAccess.denied);
    await h.pump(tester);
    expect(h.source.requests, 1);

    await tester.tap(key('run_issue_denied'));
    await tester.pumpAndSettle();
    expect(h.source.requests, 2);
    expect(h.settingsOpened, isEmpty);
    expect(key('run_start'), findsNothing);

    h.source.access = LocationAccess.granted;
    await tester.tap(key('run_issue_denied'));
    await tester.pumpAndSettle();
    expect(key('run_start'), findsOneWidget);
    expect(find.byType(RunMap), findsOneWidget);
    expect(find.byIcon(Icons.location_disabled), findsNothing);
  });

  for (final access in [
    LocationAccess.deniedForever,
    LocationAccess.serviceOff,
  ]) {
    testWidgets('${access.name}: the icon opens the app settings', (
      tester,
    ) async {
      final h = RunHarness(access: access);
      await h.pump(tester);
      await tester.tap(key('run_issue_${access.name}'));
      expect(h.settingsOpened, [1]);
      expect(h.source.requests, 1);
    });
  }

  testWidgets('a grant in settings recovers the screen on resume', (
    tester,
  ) async {
    final h = RunHarness(access: LocationAccess.deniedForever);
    await h.pump(tester);
    expect(key('run_start'), findsNothing);

    // Still refused: coming back changes nothing and never prompts.
    await _resume(tester);
    expect(key('run_start'), findsNothing);
    expect(key('run_issue_deniedForever'), findsOneWidget);

    h.source.access = LocationAccess.granted;
    await _resume(tester);
    expect(key('run_start'), findsOneWidget);
    expect(find.byType(RunMap), findsOneWidget);
    expect(find.byIcon(Icons.location_disabled), findsNothing);
    // The recheck is silent: only the open-time request ever prompted.
    expect(h.source.requests, 1);
    expect(h.source.checks, greaterThanOrEqualTo(2));
  });

  testWidgets('revoking while idle takes the map and start away on resume', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    expect(key('run_start'), findsOneWidget);
    h.source.access = LocationAccess.deniedForever;
    await _resume(tester);
    expect(key('run_start'), findsNothing);
    expect(find.byType(RunMap), findsNothing);
    expect(key('run_issue_deniedForever'), findsOneWidget);
  });

  testWidgets('resuming during a recording never re-checks access', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    await tapKey(tester, 'run_start');
    final before = h.source.checks;
    await _resume(tester);
    expect(h.source.checks, before);
    expect(key('run_pause'), findsOneWidget);
  });

  testWidgets('a start refused by a switched-off service recovers on resume', (
    tester,
  ) async {
    final h = RunHarness();
    await h.pump(tester);
    // Location goes off between the idle grant and the tap on start.
    h.source.access = LocationAccess.serviceOff;
    await tapKey(tester, 'run_start');
    expect(key('run_start'), findsNothing);
    expect(find.byType(RunMap), findsNothing);
    expect(key('run_issue_serviceOff'), findsOneWidget);

    h.source.access = LocationAccess.granted;
    await _resume(tester);
    expect(key('run_start'), findsOneWidget);
    expect(find.byType(RunMap), findsOneWidget);
    expect(find.byIcon(Icons.location_disabled), findsNothing);
  });
}
