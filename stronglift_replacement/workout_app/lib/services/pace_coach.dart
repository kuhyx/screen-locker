/// The pace target's running state: current pace, band and throttled cues.
library;

import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/pace_band.dart';

/// Tracks the current pace as accepted points arrive and fires [onCue] when
/// the runner is off the target (see [PaceCueThrottle]).
class PaceCoach {
  /// Creates a coach with no target; [onCue] hears each cue that passes.
  PaceCoach({this.onCue});

  /// Called with the cue to give.
  final void Function(PaceCue cue)? onCue;

  final _throttle = PaceCueThrottle();
  int _from = 0;

  /// The target in seconds per kilometre, or null when off.
  int? target;

  /// Pace over the last 30 s of accepted fixes, once warmed up.
  double? pace;

  /// Where [pace] stands against [target]; null with no target or no pace.
  PaceBand? get band =>
      target == null ? null : paceBandOf(current: pace, target: target!);

  /// Sets the target (null turns it off); the next off-pace fix cues at once.
  void setTarget(int? seconds) {
    target = seconds;
    _throttle.reset();
  }

  /// Starts a fresh window at [index] (the first point after a resume), so
  /// the time spent paused never reads as slow running.
  void restartAt(int index) {
    _from = index;
    pace = null;
  }

  /// Folds in the newest of [points] (accepted, oldest first).
  void update(List<RunPoint> points) {
    pace = currentPaceSeconds(points, from: _from);
    final cue = _throttle.cueFor(band, points.last.time);
    if (cue != null) onCue?.call(cue);
  }
}
