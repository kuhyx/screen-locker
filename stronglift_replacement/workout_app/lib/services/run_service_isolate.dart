// coverage:ignore-file
// Everything here runs only in the foreground-service isolate, where there is
// no widget binding a test can reach. The decisions are in run_host.dart and
// run_task_handler.dart, covered against fakes; this file only wires the real
// plugin, location source and database to them.
/// The run foreground service's entry point (the isolate the run lives in).
library;

import 'dart:async';
import 'dart:developer';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_run_replay.dart';
import 'package:workout_app/services/feedback_cues.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/position_source_location_manager.dart';
import 'package:workout_app/services/run_checkpoint_location.dart';
import 'package:workout_app/services/run_engine_recorder.dart';
import 'package:workout_app/services/run_host.dart';
import 'package:workout_app/services/run_saver.dart';
import 'package:workout_app/services/run_task_handler.dart';
import 'package:workout_app/services/storage_service.dart';

/// `FlutterForegroundTask.saveData` keys the UI isolate writes before it
/// starts the service (the service isolate cannot ask MainActivity).
const kRunFlagSandbox = 'run_sandbox';

/// See [kRunFlagSandbox].
const kRunFlagReplayFactor = 'run_replay_factor';

/// See [kRunFlagSandbox].
const kRunFlagSound = 'run_sound';

/// Entry point the plugin calls in the background isolate.
@pragma('vm:entry-point')
void runServiceStartCallback() {
  FlutterForegroundTask.setTaskHandler(_RunServiceTaskHandler());
}

/// A position source that never shows a prompt: the service has no Activity
/// to ask from, and the UI already settled the permission.
class NoPromptSource implements PositionSource {
  /// Wraps [_inner].
  NoPromptSource(this._inner);

  final PositionSource _inner;

  @override
  Future<LocationAccess> requestAccess() => _inner.checkAccess();

  @override
  Future<LocationAccess> checkAccess() => _inner.checkAccess();

  @override
  Stream<GpsFix> fixes({Duration interval = const Duration(seconds: 2)}) =>
      _inner.fixes(interval: interval);
}

class _ServicePort implements RunHostPort {
  @override
  void send(Map<String, Object?> message) =>
      FlutterForegroundTask.sendDataToMain(message);

  @override
  Future<void> notify({required String title, required String text}) async {
    await FlutterForegroundTask.updateService(
      notificationTitle: title,
      notificationText: text,
    );
  }

  @override
  Future<void> stopService() async {
    final result = await FlutterForegroundTask.stopService();
    if (result is! ServiceRequestSuccess) {
      log('RunService: stopping the service failed ($result).', level: 1000);
    }
  }

  @override
  void launchApp() => FlutterForegroundTask.launchApp();
}

Future<({bool stored, String reason})> _saveInService(RunTrack track) async {
  final result = await saveRecordedRun(
    track,
    storage: await StorageService.init(),
    // The UI isolate uploads on its next start and resume; this isolate keeps
    // the sandbox's offline guarantee (no HTTP overrides here).
    enqueue: () async => null,
  );
  return (stored: result.stored, reason: result.reason);
}

class _RunServiceTaskHandler extends TaskHandler {
  RunTaskHandler? _handler;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    Sandbox.enabled =
        await FlutterForegroundTask.getData<bool>(key: kRunFlagSandbox) ??
        false;
    Sandbox.runReplayFactor =
        await FlutterForegroundTask.getData<int>(key: kRunFlagReplayFactor) ??
        Sandbox.defaultReplayFactor;
    final cues = FeedbackCues(AudioPlayer())
      ..soundOn =
          await FlutterForegroundTask.getData<bool>(key: kRunFlagSound) ?? true;
    final port = _ServicePort();
    final host = RunHost(
      engineFactory: recorderEngineFactory(
        () => Sandbox.enabled
            ? sandboxRunSource()
            : NoPromptSource(LocationManagerPositionSource()),
      ),
      port: port,
      store: await openRunCheckpointStore(),
      cues: cues,
      save: _saveInService,
    );
    final handler = _handler = RunTaskHandler(host: host, port: port);
    debugPrint('RunService: onStart ${starter.name}');
    await handler.onStart(startedBySystem: starter == TaskStarter.system);
  }

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  void onReceiveData(Object data) => _handler?.onReceiveData(data);

  @override
  void onNotificationPressed() => _handler?.onNotificationPressed();

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    debugPrint('RunService: onDestroy timeout=$isTimeout');
    _handler?.onDestroy();
  }
}
