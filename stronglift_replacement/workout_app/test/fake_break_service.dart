/// Recording fakes for the two break-service seams.
///
/// Both stand in for a platform channel, so they record calls rather than
/// performing them — the assertions are about what the handler and the
/// controller DECIDED, which is the part that has to be right.
library;

import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_notification_text.dart';
import 'package:workout_app/services/break_service_port.dart';
import 'package:workout_app/services/foreground_break_client.dart';

/// Stands in for the real service-isolate side effects.
class FakeBreakServicePort implements BreakServicePort {
  /// Notification redraws, in order.
  final drawn = <BreakNotificationCopy>[];

  /// How many times the break-end alert fired.
  var alerts = 0;

  /// How many times the UI was nudged to drain.
  var nudges = 0;

  /// True once the service stopped itself.
  var stopped = false;

  /// True once plugins were registered in this isolate.
  var ready = false;

  @override
  Future<void> ensureIsolateReady() async => ready = true;

  @override
  Future<void> updateNotification(BreakNotificationCopy copy) async =>
      drawn.add(copy);

  @override
  Future<void> fireBreakEndAlert() async => alerts++;

  @override
  void nudgeMainToDrain() => nudges++;

  @override
  Future<void> finishAndStop() async => stopped = true;
}

/// Stands in for `flutter_foreground_task` on the UI side.
class FakeForegroundBreakClient implements ForegroundBreakClient {
  /// Creates a fake. Defaults describe a healthy Android device.
  FakeForegroundBreakClient({
    this.isSupported = true,
    this.permissionGranted = true,
    this.grantOnRequest = true,
    this.startSucceeds = true,
  });

  @override
  bool isSupported;

  /// Whether the permission is already held.
  bool permissionGranted;

  /// Whether asking for it succeeds.
  bool grantOnRequest;

  /// Whether `startService` reports success.
  bool startSucceeds;

  /// Snapshots pushed to the service, in order.
  final pushed = <BreakSnapshot>[];

  /// Calls recorded in order, for asserting sequencing.
  final calls = <String>[];

  /// The currently registered drain callback, if any.
  void Function()? onNudge;

  /// Whether a service from a previous launch is still alive.
  var running = false;

  @override
  Future<void> init() async => calls.add('init');

  @override
  Future<bool> isRunning() async {
    calls.add('isRunning');
    return running;
  }

  @override
  Future<bool> hasNotificationPermission() async {
    calls.add('hasPermission');
    return permissionGranted;
  }

  @override
  Future<bool> requestNotificationPermission() async {
    calls.add('requestPermission');
    return permissionGranted = grantOnRequest;
  }

  @override
  Future<bool> start(BreakSnapshot snapshot) async {
    calls.add('start');
    if (startSucceeds) pushed.add(snapshot);
    return startSucceeds;
  }

  @override
  Future<void> push(BreakSnapshot snapshot) async {
    calls.add('push');
    pushed.add(snapshot);
  }

  @override
  Future<void> stop() async {
    calls.add('stop');
    running = false;
  }

  @override
  void listenForDrainNudges(void Function() onNudge) {
    calls.add('listen');
    this.onNudge = onNudge;
  }

  @override
  void stopListeningForDrainNudges() {
    calls.add('unlisten');
    onNudge = null;
  }
}
