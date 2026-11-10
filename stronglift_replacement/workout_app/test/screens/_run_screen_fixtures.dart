// Shared harness for the run screen tests: every dependency is an in-memory
// fake, so nothing here needs the real event loop or the database.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_run_service.dart';
import '../fake_run_uploader.dart';
import '../run_test_fixtures.dart';

/// Everything a test needs to drive and inspect one screen.
class RunHarness {
  RunHarness({
    LocationAccess access = LocationAccess.granted,
    ManualPositionSource? source,
    FakeForegroundRunClient? service,
    this.saveThrows = false,
    this.saveGate,
  }) : source = source ?? ManualPositionSource(access: access),
       service = service ?? FakeForegroundRunClient();

  final ManualPositionSource source;
  final FakeForegroundRunClient service;
  final bool saveThrows;
  final Completer<void>? saveGate;
  final uploader = FakeRunUploader();
  final cues = QuietCues();
  final saved = <RunTrack>[];
  final settingsOpened = <int>[];
  final navigator = GlobalKey<NavigatorState>();

  RunController build() => RunController(
    sourceFor: (_) => source,
    service: service,
    cues: cues,
    save: (track) async {
      await saveGate?.future;
      if (saveThrows) throw Exception('disk full');
      saved.add(track);
      return const RunSaveResult(stored: true, reason: 'saved');
    },
  );

  Widget app() => MaterialApp(
    navigatorKey: navigator,
    theme: buildAppTheme(),
    home: const SizedBox(),
  );

  RunScreen screen({
    Widget Function(BuildContext, ValueListenable<List<RunPoint>>)? mapBuilder,
  }) => RunScreen(
    controllerFactory: build,
    uploader: uploader,
    mapBuilder: mapBuilder,
    openSettings: () async {
      settingsOpened.add(1);
      return true;
    },
  );

  /// Pumps the app with the run screen pushed on top of an empty route.
  Future<void> pump(
    WidgetTester tester, {
    Widget Function(BuildContext, ValueListenable<List<RunPoint>>)? mapBuilder,
  }) async {
    await tester.pumpWidget(app());
    navigator.currentState!.push(
      MaterialPageRoute<void>(builder: (_) => screen(mapBuilder: mapBuilder)),
    );
    await tester.pumpAndSettle();
  }

  /// Feeds [count] fixes 2 s apart at 3 m/s and lets the screen redraw.
  Future<void> run(WidgetTester tester, int count, {int from = 0}) async {
    straightRun(count, startSecond: from * 2).forEach(source.controller.add);
    await tester.pumpAndSettle();
  }
}

Finder key(String id) => find.byKey(Key(id));

Future<void> tapKey(WidgetTester tester, String id) async {
  await tester.tap(key(id));
  // Stream cancel only completes on the real event loop, so give it a turn
  // before settling the frames.
  await tester.runAsync(
    () => Future<void>.delayed(const Duration(milliseconds: 10)),
  );
  await tester.pumpAndSettle();
}
