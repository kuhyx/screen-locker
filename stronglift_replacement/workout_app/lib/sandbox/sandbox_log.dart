/// The sandbox's trace: every tap, break, save and navigation, to logcat.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:workout_app/sandbox/sandbox.dart';

/// Writes one line per event under the `WorkoutSandbox` logcat tag.
///
/// A no-op in the daily build, so call sites can stay unconditional. Lines
/// also go through [debugPrint], which is what `flutter run` shows.
abstract final class SandboxLog {
  static bool _channelDown = false;

  /// Records [event] with optional [details], e.g.
  /// `SandboxLog.event('tap set', {'exercise': 'Squat', 'set': 2})`.
  static void event(String event, [Map<String, Object?> details = const {}]) {
    if (!Sandbox.enabled) return;
    final line = details.isEmpty ? event : '$event $details';
    debugPrint('WorkoutSandbox: $line');
    unawaited(_toLogcat(line));
  }

  static Future<void> _toLogcat(String line) async {
    if (_channelDown) return;
    try {
      await Sandbox.channel.invokeMethod<void>('log', line);
    } on MissingPluginException catch (error) {
      // Said once, then the trace lives in debugPrint alone: repeating this
      // on every event would drown the trace it is warning about.
      _channelDown = true;
      debugPrint(
        'WorkoutSandbox: logcat channel unavailable ($error) — the trace '
        'continues in flutter logs only.',
      );
    }
  }

  /// Forgets a failed channel so the next event retries it.
  @visibleForTesting
  static void resetForTesting() => _channelDown = false;
}
