/// A run screen/controller over the in-process host and a fake engine: the
/// run lives in the rig, so a test can throw the screen away and look at it.
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart' show WidgetTester, addTearDown;
import 'package:material_ui/material_ui.dart';
import 'package:workout_app/screens/run_screen.dart';
import 'package:workout_app/services/run_controller.dart';
import 'package:workout_app/services/run_link.dart';
import 'package:workout_app/ui/theme.dart';

import 'fake_run_engine.dart';
import 'fake_run_service.dart';
import 'fake_run_uploader.dart';
import 'run_host_rig.dart';
import 'run_test_fixtures.dart';
import 'screens/_run_screen_helpers.dart';

/// The in-process host the controllers talk to, shared by every controller
/// the rig builds (as the real service is shared by every screen).
class PersistRig {
  /// Creates the rig; [supported] says whether a service exists.
  PersistRig({bool supported = true})
    : service = FakeForegroundRunClient(isSupported: supported) {
    port = LoopbackRunPort(service);
    host = HostRig(hostPort: port);
    addTearDown(host.host.dispose);
    link = _RigLink(this);
  }

  /// The fake Android service.
  final FakeForegroundRunClient service;

  /// The host and its recorded collaborators.
  late final HostRig host;

  /// The port the host would use (loopback to [service]).
  late final LoopbackRunPort port;

  /// The link every controller gets.
  late final RunHostLink link;

  /// Controllers built, oldest first.
  final controllers = <RunController>[];

  final uploader = FakeRunUploader();
  final paceStore = MemoryPaceStore();
  final navigator = GlobalKey<NavigatorState>();

  /// The newest engine.
  FakeRunEngine get engine => host.engine;

  /// A controller over the shared host and an idle source that grants.
  RunController build() {
    final c = RunController(
      idleSourceFor: ManualPositionSource.new,
      service: service,
      link: link,
      soundOn: () async => true,
      hostTimeout: const Duration(milliseconds: 200),
      retryEvery: const Duration(milliseconds: 1),
    );
    controllers.add(c);
    return c;
  }

  /// A screen over [build].
  RunScreen screen({bool resuming = false}) => RunScreen(
    controllerFactory: build,
    uploader: uploader,
    paceStore: paceStore,
    mapBuilder: fakeTileMap,
    resuming: resuming,
  );

  /// Pumps an app with the run screen pushed on an empty route.
  Future<void> pump(WidgetTester tester, {bool resuming = false}) async {
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigator,
        theme: buildAppTheme(),
        home: const SizedBox(),
      ),
    );
    navigator.currentState!.push(
      MaterialPageRoute<void>(builder: (_) => screen(resuming: resuming)),
    );
    await tester.pumpAndSettle();
  }
}

/// Sends commands to the rig's host and relays its snapshots.
class _RigLink implements RunHostLink {
  _RigLink(this._rig);

  final PersistRig _rig;

  @override
  Stream<Map<Object?, Object?>> get messages => _rig.port.messages;

  @override
  void send(Map<String, Object?> command) => unawaited(
    _rig.host.host.handle(command),
  );

  @override
  Future<void> close() async {}
}
