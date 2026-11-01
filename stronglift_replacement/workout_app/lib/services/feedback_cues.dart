/// The haptic and sound cues the workout screen gives for what the user DID.
library;

import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/storage_service.dart';

/// Cues for recording a set and finishing a workout.
///
/// They reward the RECORDING, never the number recorded: a deloaded or failed
/// set and workout get exactly the confirmation a personal best does, so the
/// app cannot nudge anyone towards misreporting. Nothing here fires for a
/// deletion. Every sound has a haptic sibling that fires regardless of the
/// sound switch, because sound is the channel that fails (silenced phone,
/// noisy gym) and the haptic carries the meaning alone.
class FeedbackCues {
  /// Creates cues that play on [_player].
  FeedbackCues(this._player);

  final AudioPlayer _player;

  /// Whether sound may play. Ships on; [load] replaces it with the stored
  /// choice, so a cue that fires before the read lands is still audible.
  bool soundOn = true;

  /// Reads the stored sound choice.
  Future<void> load() async {
    soundOn = await StorageService.instance.getSoundEnabled();
  }

  /// A set (or warmup) was just recorded: a light click, on the tap itself.
  void setRecorded() {
    SandboxLog.event('cue set recorded', {'haptic': 'selectionClick'});
    unawaited(HapticFeedback.selectionClick());
  }

  /// The workout was just finished: a firmer tap and, if allowed, a chime.
  Future<void> workoutFinished() async {
    SandboxLog.event('cue workout finished', {
      'haptic': 'mediumImpact',
      'sound': soundOn,
    });
    unawaited(HapticFeedback.mediumImpact());
    if (!soundOn) return;
    await _player.play(AssetSource('sounds/workout_done.wav')).catchError((
      Object error,
    ) {
      // Never fatal, never silent: a chime that did not play must show up in
      // the log, or "no sound" is indistinguishable from "no cue".
      debugPrint('WorkoutApp: finish chime failed to play ($error).');
    });
  }
}
