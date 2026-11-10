/// The real run foreground-service client, and the service's entry point.
library;

import 'dart:io' show Platform;

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:workout_app/services/break_notification_text.dart';
import 'package:workout_app/services/foreground_run_client.dart';

/// Channel the ongoing run notification lives on.
///
/// Low importance (it is on screen for the whole run and must never buzz) and
/// versioned for the same reason as the workout one: channel settings freeze
/// on first creation. The name is a symbol, not a word (textgate): Android
/// shows it in system settings.
const kRunOngoingChannelId = 'run_ongoing_v1';

// coverage:ignore-start
/// Entry point the plugin calls in the background isolate.
///
/// The handler does nothing: the recorder lives in the UI isolate. The
/// service exists to keep that isolate's process alive, to hold the wake lock
/// and to own the notification.
@pragma('vm:entry-point')
void runServiceStartCallback() {
  FlutterForegroundTask.setTaskHandler(_RunServiceTaskHandler());
}

class _RunServiceTaskHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  void onNotificationPressed() => FlutterForegroundTask.launchApp();

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {}
}
// coverage:ignore-end

/// The real [ForegroundRunClient], driving `flutter_foreground_task`.
class FlutterForegroundRunClient implements ForegroundRunClient {
  /// Creates a client. Cheap: nothing happens until [start].
  FlutterForegroundRunClient();

  @override
  bool get isSupported => Platform.isAndroid;

  // Platform-channel passthroughs. `flutter test` runs on Linux, where
  // isSupported is false and none of this is reachable; the decisions that
  // lead here live in run_controller.dart, covered against a fake.
  // coverage:ignore-start

  @override
  Future<bool> hasNotificationPermission() async =>
      await FlutterForegroundTask.checkNotificationPermission() ==
      NotificationPermission.granted;

  @override
  Future<bool> requestNotificationPermission() async =>
      await FlutterForegroundTask.requestNotificationPermission() ==
      NotificationPermission.granted;

  @override
  Future<bool> start({
    required bool withLocation,
    required String title,
    required String text,
  }) async {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: kRunOngoingChannelId,
        // App name only (textgate settled decision 4); was the runner emoji.
        channelName: BreakNotificationText.channelName,
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        // allowWakeLock stays at its default (true): it is why GPS fixes keep
        // arriving with the screen off.
      ),
    );
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
    final result = await FlutterForegroundTask.startService(
      serviceTypes: [
        ForegroundServiceTypes.dataSync,
        if (withLocation) ForegroundServiceTypes.location,
      ],
      notificationTitle: title,
      notificationText: text,
      callback: runServiceStartCallback,
    );
    return result is ServiceRequestSuccess;
  }

  @override
  Future<void> update({required String title, required String text}) async {
    await FlutterForegroundTask.updateService(
      notificationTitle: title,
      notificationText: text,
    );
  }

  @override
  Future<void> stop() async {
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  // coverage:ignore-end
}
