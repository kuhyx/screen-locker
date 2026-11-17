/// The real run foreground-service client and the UI's real link to its host.
library;

import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/break_notification_text.dart';
import 'package:workout_app/services/foreground_run_client.dart';
import 'package:workout_app/services/run_link.dart';
import 'package:workout_app/services/run_service_isolate.dart';
import 'package:workout_app/services/run_wire.dart';
import 'package:workout_app/services/storage_service.dart';

/// Channel the ongoing run notification lives on.
///
/// Low importance (it is on screen for the whole run and must never buzz) and
/// versioned for the same reason as the workout one: channel settings freeze
/// on first creation. The name is a symbol, not a word (textgate): Android
/// shows it in system settings.
const kRunOngoingChannelId = 'run_ongoing_v1';

/// The real [ForegroundRunClient], driving `flutter_foreground_task`.
class FlutterForegroundRunClient implements ForegroundRunClient {
  /// Creates a client. Cheap: nothing happens until [start].
  FlutterForegroundRunClient();

  @override
  bool get isSupported => Platform.isAndroid;

  // Platform-channel passthroughs. `flutter test` runs on Linux, where
  // isSupported is false and none of this is reachable; the decisions that
  // lead here live in run_controller.dart and run_host.dart, covered against
  // fakes.
  // coverage:ignore-start

  @override
  Future<bool> hasNotificationPermission() async =>
      await FlutterForegroundTask.checkNotificationPermission() ==
      NotificationPermission.granted;

  @override
  Future<bool> requestNotificationPermission() async =>
      await FlutterForegroundTask.requestNotificationPermission() ==
      NotificationPermission.granted;

  /// Starts the service, or leaves a running one alone: a live service may be
  /// hosting a run, and replacing it would end that run.
  @override
  Future<bool> start({
    required bool withLocation,
    required String title,
    required String text,
  }) async {
    if (await FlutterForegroundTask.isRunningService) return true;
    await _saveFlags();
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
        // The run must come back by itself after a reboot, and the plugin
        // restarts a killed service (allowAutoRestart defaults to true).
        // allowWakeLock stays at its default (true): it is why GPS fixes keep
        // arriving with the screen off.
        autoRunOnBoot: true,
      ),
    );
    final result = await FlutterForegroundTask.startService(
      // `location` alone: Android 15 refuses a dataSync service from the boot
      // broadcast, and dataSync has a 6 h budget a long run can exhaust.
      serviceTypes: [ForegroundServiceTypes.location],
      notificationTitle: title,
      notificationText: text,
      callback: runServiceStartCallback,
    );
    return result is ServiceRequestSuccess;
  }

  Future<void> _saveFlags() async {
    await FlutterForegroundTask.saveData(
      key: kRunFlagSandbox,
      value: Sandbox.enabled,
    );
    await FlutterForegroundTask.saveData(
      key: kRunFlagReplayFactor,
      value: Sandbox.runReplayFactor,
    );
    await FlutterForegroundTask.saveData(
      key: kRunFlagSound,
      value: await StorageService.instance.getSoundEnabled(),
    );
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

/// The UI's link to the host in the service isolate.
// coverage:ignore-start
class ServiceRunLink implements RunHostLink {
  /// Listens for the host's messages until [close].
  ServiceRunLink() {
    FlutterForegroundTask.addTaskDataCallback(_onData);
  }

  final _out = StreamController<Map<Object?, Object?>>.broadcast();

  void _onData(Object data) {
    // The break service shares this channel; only run messages pass.
    if (isRunMessage(data)) _out.add(data as Map<Object?, Object?>);
  }

  @override
  Stream<Map<Object?, Object?>> get messages => _out.stream;

  @override
  void send(Map<String, Object?> command) =>
      FlutterForegroundTask.sendDataToTask(command);

  @override
  Future<void> close() async {
    FlutterForegroundTask.removeTaskDataCallback(_onData);
    await _out.close();
  }
}

// coverage:ignore-end
