/// The sandbox flavor: a second install that can be poked at without fear.
///
/// `com.kuhy.workout_app.sandbox` is a separate package, so Android already
/// keeps its database, secure storage and notifications apart from the daily
/// build. This class carries the rest of the isolation into Dart: no network,
/// no LAN server for the PC to pull from, its own `/sdcard` paths, and a
/// rest length short enough to watch a break start and end in one sitting.
library;

import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter/services.dart';

/// Build-time facts about the running flavor, resolved once at startup.
abstract final class Sandbox {
  /// Channel MainActivity answers on; also carries the logcat trace.
  static const MethodChannel channel = MethodChannel(
    'com.kuhy.workout_app/sandbox',
  );

  /// Where the sandbox mirrors its backups, beside — never inside — the
  /// daily build's `/sdcard/WorkoutTracker`.
  static const String backupDir = '/sdcard/WorkoutTrackerSandbox';

  /// Where the sandbox writes finished workouts; the PC never reads this.
  static const String syncFilePath = '/sdcard/workout_result_sandbox.json';

  /// Rest length used when no override has been saved yet.
  static const int defaultRestSecs = 5;

  /// Whether this process is the sandbox flavor. Set once by [init]; tests
  /// assign it directly to exercise both flavors in one process.
  static bool enabled = false;

  /// Rest length (seconds) every break uses while [enabled]; persisted by
  /// the Settings screen, loaded by `main`.
  static int restSecs = defaultRestSecs;

  /// Environment variable that turns the sandbox on where there is no
  /// flavor to ask — the Linux desktop build, run under Xvfb to check a
  /// change on the PC before it goes anywhere near the phone.
  static const String envVar = 'WORKOUT_SANDBOX';

  /// Asks the platform which flavor built this process, or, where there is
  /// no MainActivity to ask (Linux, tests), reads [envVar].
  static Future<void> init([Map<String, String>? environment]) async {
    try {
      enabled = await channel.invokeMethod<bool>('isSandbox') ?? false;
    } on MissingPluginException catch (error) {
      enabled = (environment ?? Platform.environment)[envVar] == '1';
      debugPrint(
        'WorkoutApp: no sandbox channel on this platform ($error) — '
        '$envVar=${enabled ? '1: sandbox' : 'unset: daily build'}.',
      );
    }
  }

  /// [defaultSecs] for the daily build, the override for the sandbox.
  static int rest(int defaultSecs) => enabled ? restSecs : defaultSecs;

  /// [defaultLabel] for the daily build; the sandbox names its real length
  /// so a 5 s countdown is never captioned "3 min".
  static String restLabel(String defaultLabel) =>
      enabled ? 'Rest ($restSecs s — sandbox)' : defaultLabel;
}
