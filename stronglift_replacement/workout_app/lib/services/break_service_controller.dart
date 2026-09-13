/// Owns the foreground service on behalf of the workout screen.
library;

import 'dart:async';
import 'dart:developer';

import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/foreground_break_client.dart';

/// Stops a break service left running by a workout that no longer exists.
///
/// The service deliberately outlives its screen — the back button pops the
/// workout while it carries on in the database — and `stopWithTask="false"`
/// means it also outlives the task being swiped away. That is the point, but
/// it means a crash between "service started" and "workout finished" would
/// otherwise leave a notification counting down forever with nothing behind
/// it. Called once at startup, when the answer is knowable.
Future<bool> stopStaleBreakService(
  ForegroundBreakClient client, {
  required Future<bool> Function() hasActiveWorkout,
}) async {
  if (!client.isSupported) return false;
  if (!await client.isRunning()) return false;
  if (await hasActiveWorkout()) return false;
  log(
    'WorkoutApp: a break service was still running with no workout in '
    'progress — stopping it. Its notification was counting down a session '
    'that had already ended.',
    level: 900,
  );
  await client.stop();
  return true;
}

/// Starts the service, keeps it fed, and applies what the user pressed.
///
/// Pulled out of `WorkoutScreen` so the permission handling, the failure
/// reporting and the drain scheduling can be tested without a device — the
/// screen keeps only the parts that need `setState`.
class BreakServiceController {
  /// Creates a controller over [client] and [queue].
  BreakServiceController(this._client, this._queue);

  final ForegroundBreakClient _client;
  final BreakIntentQueue _queue;

  var _started = false;

  /// True once the service has been started for this workout.
  bool get isStarted => _started;

  /// Starts the service for [snapshot] and begins listening for nudges.
  ///
  /// Returns what actually happened, so the screen can tell the user when the
  /// notification will not appear. A denied permission does NOT stop the
  /// service: its isolate still holds the wake lock and still plays the
  /// break-end sound, so the alert survives even when the status bar is empty.
  Future<BreakServiceStartResult> start(
    BreakSnapshot snapshot, {
    required void Function() onDrainNudge,
  }) async {
    if (!_client.isSupported) return BreakServiceStartResult.unsupported;

    await _client.init();
    var notificationsAllowed = await _client.hasNotificationPermission();
    if (!notificationsAllowed) {
      notificationsAllowed = await _client.requestNotificationPermission();
    }
    if (!notificationsAllowed) {
      log(
        'WorkoutScreen: notification permission denied. The rest timer still '
        'runs and the break-end sound still plays, but the status-bar '
        'countdown and its Done / − 1 rep / Skip buttons cannot be shown. '
        'Grant it in Settings > Apps > Workout Tracker > Notifications.',
        level: 1000,
      );
    }

    _client.listenForDrainNudges(onDrainNudge);
    final ok = await _client.start(snapshot);
    if (!ok) {
      _client.stopListeningForDrainNudges();
      log(
        'WorkoutScreen: the foreground break service refused to start. The '
        'in-app countdown still works, but it will stall if the phone sleeps '
        '— keep the app open for this workout.',
        level: 1000,
      );
      return BreakServiceStartResult.failed;
    }
    _started = true;
    return notificationsAllowed
        ? BreakServiceStartResult.started
        : BreakServiceStartResult.startedWithoutNotification;
  }

  /// Sends the service the current state of the workout.
  Future<void> push(BreakSnapshot snapshot) async {
    if (!_started) return;
    await _client.push(snapshot);
  }

  /// Stops the service and forgets any presses that were never applied.
  Future<void> stop() async {
    if (!_client.isSupported) return;
    _client.stopListeningForDrainNudges();
    if (_started) {
      await _client.stop();
      _started = false;
    }
    await _queue.clear();
  }

  /// Applies every press the screen has not seen yet, via [apply].
  ///
  /// A platform with no foreground service has no notification to press, so
  /// there is nothing to drain and no reason to touch the queue's storage.
  Future<void> drain(Future<void> Function(BreakIntent intent) apply) async {
    if (!_client.isSupported) return;
    await _queue.drain(apply);
  }
}
