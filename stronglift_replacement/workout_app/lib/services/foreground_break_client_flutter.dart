/// The real foreground-service client, and the service's entry point.
library;

import 'dart:io' show Platform;

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';
import 'package:workout_app/services/break_service_port.dart';
import 'package:workout_app/services/break_service_port_flutter.dart';
import 'package:workout_app/services/break_task_handler.dart';
import 'package:workout_app/services/foreground_break_client.dart';

/// Channel the ongoing workout notification lives on.
///
/// Separate from `break_end_v1` and deliberately LOW importance: this one is on
/// screen for the whole workout, so it must never buzz. The alert is the other
/// channel's job. Versioned for the same reason — channel settings freeze on
/// first creation and cannot be edited afterwards.
const kWorkoutOngoingChannelId = 'workout_ongoing_v1';

/// Button labels, parallel to [BreakNotificationAction.inButtonOrder].
const _buttonLabels = ['✓ Done', '− 1 rep', 'Skip break'];

/// Entry point the plugin calls in the background isolate.
// coverage:ignore-start
@pragma('vm:entry-point')
void breakServiceStartCallback() {
  // Only ever invoked by flutter_foreground_task's isolate bootstrap; there is
  // no isolate in `flutter test` that can reach it. Everything it builds is
  // covered in break_task_handler_test.dart against a fake port.
  FlutterForegroundTask.setTaskHandler(
    _BreakServiceTaskHandler(
      BreakTaskHandler(
        FlutterBreakServicePort(),
        BreakIntentQueue(PrefsBreakIntentStore()),
      ),
    ),
  );
}

/// Adapts the plugin's callback shape onto the testable [BreakTaskHandler].
///
/// Only the background isolate constructs or calls this. Each override is a
/// single delegation; the logic behind it is covered against a fake port.
class _BreakServiceTaskHandler extends TaskHandler {
  _BreakServiceTaskHandler(this._handler);

  final BreakTaskHandler _handler;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) =>
      _handler.start(null, timestamp);

  @override
  void onRepeatEvent(DateTime timestamp) => _handler.tick(timestamp);

  @override
  void onReceiveData(Object data) =>
      _handler.receiveData(data, DateTime.now());

  @override
  void onNotificationButtonPressed(String id) =>
      _handler.pressButton(id, DateTime.now());

  @override
  void onNotificationPressed() => FlutterForegroundTask.launchApp();

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {}
}
// coverage:ignore-end

/// The real [ForegroundBreakClient], driving `flutter_foreground_task`.
class FlutterForegroundBreakClient implements ForegroundBreakClient {
  /// Creates a client. Cheap: nothing happens until [init].
  FlutterForegroundBreakClient();

  void Function()? _onNudge;

  @override
  bool get isSupported => Platform.isAndroid;

  // Platform-channel passthroughs. `flutter test` runs on Linux, where
  // isSupported is false and none of this is reachable; the decisions that
  // lead here live in break_service_controller.dart, covered against a fake.
  // coverage:ignore-start

  @override
  Future<void> init() async {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: kWorkoutOngoingChannelId,
        channelName: 'Workout in progress',
        channelDescription:
            'Shows the rest countdown and the next set while a workout '
            'runs. Kept silent on purpose: the break-end alert has its own '
            'channel.',
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(1000),
        // NOTE: allowWakeLock and allowAutoRestart both default to true and
        // the linter rejects restating them, but they are load-bearing.
        // The wake lock is why the deadline still fires with the screen
        // off; without it this whole feature is the bug it replaces.
      ),
    );
  }

  @override
  Future<bool> isRunning() => FlutterForegroundTask.isRunningService;

  @override
  Future<bool> hasNotificationPermission() async =>
      await FlutterForegroundTask.checkNotificationPermission() ==
      NotificationPermission.granted;

  @override
  Future<bool> requestNotificationPermission() async =>
      await FlutterForegroundTask.requestNotificationPermission() ==
      NotificationPermission.granted;

  @override
  Future<bool> start(BreakSnapshot snapshot) async {
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
    final result = await FlutterForegroundTask.startService(
      serviceTypes: [ForegroundServiceTypes.dataSync],
      notificationTitle: 'Workout ${snapshot.workoutType}',
      notificationText: 'Starting…',
      notificationButtons: [
        for (final (i, id) in BreakNotificationAction.inButtonOrder.indexed)
          NotificationButton(id: id, text: _buttonLabels[i]),
      ],
      callback: breakServiceStartCallback,
    );
    if (result is! ServiceRequestSuccess) return false;
    await push(snapshot);
    return true;
  }

  @override
  Future<void> push(BreakSnapshot snapshot) async =>
      FlutterForegroundTask.sendDataToTask(snapshot.toMap());

  @override
  Future<void> stop() async {
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  @override
  void listenForDrainNudges(void Function() onNudge) {
    stopListeningForDrainNudges();
    _onNudge = onNudge;
    FlutterForegroundTask.addTaskDataCallback(_handleTaskData);
  }

  @override
  void stopListeningForDrainNudges() {
    FlutterForegroundTask.removeTaskDataCallback(_handleTaskData);
    _onNudge = null;
  }

  /// The service's nudge carries no payload -- see [BreakServicePort]. Any
  /// message from the task isolate means "the queue has something in it".
  void _handleTaskData(Object data) => _onNudge?.call();

  // coverage:ignore-end
}
