/// The haptic and sound cues the workout screen gives for what the user DID.
library;

import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:vibration/vibration.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/storage_service.dart';

/// The vibration pattern (pause, buzz, pause, buzz ... in ms) of a pace cue:
/// one long buzz to speed up, three short ones to ease off. Both differ from
/// the kilometre double buzz.
List<int> paceCuePattern(PaceCue cue) => switch (cue) {
  PaceCue.tooSlow => const [0, 700],
  PaceCue.tooFast => const [0, 90, 70, 90, 70, 90],
};

/// The tone of a pace cue: falling to speed up, rising to ease off.
String paceCueSound(PaceCue cue) => switch (cue) {
  PaceCue.tooSlow => 'sounds/pace_slow.wav',
  PaceCue.tooFast => 'sounds/pace_fast.wav',
};

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

  /// A whole kilometre of a run was just credited: a double buzz and, if
  /// allowed, the chime.
  ///
  /// The vibration plugin rather than [HapticFeedback]: a run happens with the
  /// screen off in a pocket, where view haptics may not fire.
  Future<void> kilometreReached(int km) async {
    SandboxLog.event('cue kilometre', {'km': km, 'sound': soundOn});
    if (await Vibration.hasVibrator()) {
      // Android/iOS-only: hasVibrator() is false on the Linux test host.
      // coverage:ignore-start
      unawaited(Vibration.vibrate(pattern: [0, 150, 100, 150]));
      // coverage:ignore-end
    }
    if (!soundOn) return;
    await _player.play(AssetSource('sounds/workout_done.wav')).catchError((
      Object error,
    ) {
      debugPrint('WorkoutApp: kilometre chime failed to play ($error).');
    });
  }

  /// The runner left the pace band: the cue's buzz pattern and, if allowed,
  /// its tone. Silent while on pace (the caller only calls this off pace).
  Future<void> paceOff(PaceCue cue) async {
    SandboxLog.event('cue pace', {'cue': cue.name, 'sound': soundOn});
    if (await Vibration.hasVibrator()) {
      // Android/iOS-only: hasVibrator() is false on the Linux test host.
      // coverage:ignore-start
      unawaited(Vibration.vibrate(pattern: paceCuePattern(cue)));
      // coverage:ignore-end
    }
    if (!soundOn) return;
    await _player.play(AssetSource(paceCueSound(cue))).catchError((
      Object error,
    ) {
      debugPrint('WorkoutApp: pace tone failed to play ($error).');
    });
  }
}
