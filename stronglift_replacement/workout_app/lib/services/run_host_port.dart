/// The host's way out to the rest of the phone, and its two small types.
library;

import 'dart:async';
import 'dart:developer';

import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_checkpoint_store.dart';

/// The host's way out to the rest of the phone.
abstract interface class RunHostPort {
  /// Sends [message] to the UI (dropped when no UI is listening).
  void send(Map<String, Object?> message);

  /// Redraws the ongoing notification.
  Future<void> notify({required String title, required String text});

  /// Stops the foreground service (the run is over and saved).
  Future<void> stopService();

  /// Brings the app to the front.
  void launchApp();
}

/// Saves a finished track; the reason reads like a sentence.
typedef RunSaveFn =
    Future<({bool stored, String reason})> Function(RunTrack track);

/// Marks a notification title as carrying advice to finish: symbols only
/// (textgate), one per reason.
String suggestionGlyph(String why) => switch (why) {
  'stationary' => '⏸',
  'vehicleSpeed' => '⚡',
  'gpsLost' => '⌖',
  _ => '↻',
};

/// Stores [checkpoint] (when there is one) without waiting; a failed write is
/// logged, never swallowed.
void saveCheckpointLoudly(RunCheckpointStore store, RunCheckpoint? checkpoint) {
  if (checkpoint == null) return;
  unawaited(
    store.save(checkpoint).catchError((Object error, StackTrace stack) {
      log(
        'RunHost: could not save the run checkpoint ($error) -- a dead '
        'process would lose the run since the last good save.',
        level: 1000,
        error: error,
        stackTrace: stack,
      );
    }),
  );
}
