// Shared harness for the run screen tests: every dependency is an in-memory
// fake, so nothing here needs the real event loop or the database.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/pace_target_store.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_engine_recorder.dart';
import 'package:workout_app/services/run_link.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/run_map_slot.dart';

import '../fake_run_service.dart';
import '../fake_run_uploader.dart';
import '../run_test_fixtures.dart';
import '_run_screen_helpers.dart';

export '_run_screen_helpers.dart';

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
  final paceStore = MemoryPaceStore();
  final saved = <RunTrack>[];
  final settingsOpened = <int>[];
  final navigator = GlobalKey<NavigatorState>();

  RunController build() {
    final link = LoopbackRunLink.build(
      client: service,
      engineFactory: recorderEngineFactory(() => source),
      cues: cues,
      save: (track) async {
        await saveGate?.future;
        if (saveThrows) throw Exception('disk full');
        saved.add(track);
        return (stored: true, reason: 'saved');
      },
    );
    // The run outlives the screen, so the test ends it (the recorder keeps a
    // watchdog timer).
    addTearDown(link.host.dispose);
    return RunController(
      idleSourceFor: () => source,
      service: service,
      link: link,
      soundOn: () async => true,
    );
  }

  Widget app() => MaterialApp(
    navigatorKey: navigator,
    theme: buildAppTheme(),
    home: const SizedBox(),
  );

  /// The screen over [mapBuilder], fake tiles by default; [realMap] leaves
  /// the screen's own default map in place.
  RunScreen screen({RunMapBuilder? mapBuilder, bool realMap = false}) =>
      RunScreen(
        controllerFactory: build,
        uploader: uploader,
        paceStore: paceStore,
        mapBuilder: realMap ? null : mapBuilder ?? fakeTileMap,
        openSettings: () async {
          settingsOpened.add(1);
          return true;
        },
      );

  /// Pumps the app with the run screen pushed on top of an empty route.
  Future<void> pump(
    WidgetTester tester, {
    RunMapBuilder? mapBuilder,
    bool realMap = false,
  }) async {
    await tester.pumpWidget(app());
    navigator.currentState!.push(
      MaterialPageRoute<void>(
        builder: (_) => screen(mapBuilder: mapBuilder, realMap: realMap),
      ),
    );
    await tester.pumpAndSettle();
  }

  /// Feeds [count] fixes 2 s apart at 3 m/s and lets the screen redraw.
  Future<void> run(WidgetTester tester, int count, {int from = 0}) async {
    straightRun(count, startSecond: from * 2).forEach(source.controller.add);
    await tester.pumpAndSettle();
  }
}
