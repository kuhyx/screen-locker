/// The optional pace target: current pace, the band around the target and the
/// cue throttle. Pure Dart, no clock of its own -- everything runs on fix time,
/// so it is deterministic in tests and right at the sandbox's replay speed.
library;

import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_math.dart';

/// The trailing window, in seconds of fix time, the current pace is read over.
const int kPaceWindowSeconds = 30;

/// The window must span at least this long before a pace is reported: the
/// first fixes of a run (or after a resume) say nothing yet.
const int kPaceWarmupSeconds = 20;

/// Half-width of the band around the target, in seconds per kilometre.
const int kPaceToleranceSeconds = 10;

/// The least time between two cues, in seconds of fix time.
const int kPaceCueGapSeconds = 30;

/// Fastest target, 3:00 per kilometre.
const int kMinPaceTarget = 180;

/// Slowest target, 12:00 per kilometre.
const int kMaxPaceTarget = 720;

/// The picker's step, in seconds per kilometre.
const int kPaceStep = 5;

/// [seconds] rounded to a [kPaceStep] and held inside the target range.
int clampPaceTarget(int seconds) => ((seconds / kPaceStep).round() * kPaceStep)
    .clamp(kMinPaceTarget, kMaxPaceTarget);

/// Pace in seconds per kilometre over the last [kPaceWindowSeconds] of
/// [points], reading only from index [from] on (the first point after a
/// resume, so the time spent paused never counts as slow running).
///
/// Null while the window spans under [kPaceWarmupSeconds], and null when it
/// moved slower than [kMinMovingSpeedMps]: standing still is not a pace, so it
/// earns neither a colour nor a cue (the pause button is for that).
double? currentPaceSeconds(List<RunPoint> points, {int from = 0}) {
  if (points.length - from < 2) return null;
  final last = points.last;
  var oldest = points.length - 1;
  while (oldest > from &&
      last.time.difference(points[oldest - 1].time).inSeconds <=
          kPaceWindowSeconds) {
    oldest--;
  }
  final span = last.time.difference(points[oldest].time).inMilliseconds / 1000;
  if (span < kPaceWarmupSeconds) return null;
  final metres = last.distanceM - points[oldest].distanceM;
  if (metres / span < kMinMovingSpeedMps) return null;
  return span / (metres / 1000);
}

/// Where the current pace stands against the target.
enum PaceBand {
  /// Within the tolerance, ends included.
  onPace,

  /// Slower than the band (more seconds per kilometre).
  tooSlow,

  /// Faster than the band (fewer seconds per kilometre).
  tooFast,
}

/// The band [current] falls in around [target], or null with no pace yet.
PaceBand? paceBandOf({required double? current, required int target}) {
  if (current == null) return null;
  final off = current - target;
  if (off > kPaceToleranceSeconds) return PaceBand.tooSlow;
  if (off < -kPaceToleranceSeconds) return PaceBand.tooFast;
  return PaceBand.onPace;
}

/// What the runner is told when off pace.
enum PaceCue {
  /// Speed up.
  tooSlow,

  /// Ease off.
  tooFast,
}

/// Lets a cue through at most once per [kPaceCueGapSeconds] of fix time.
///
/// On pace it is silent. Coming back into the band does not reset the gap, so
/// drifting in and out cannot nag; and a slow-to-fast flip inside the gap is
/// held back too.
class PaceCueThrottle {
  DateTime? _last;

  /// The cue for [band] at fix time [at], or null when silent or throttled.
  PaceCue? cueFor(PaceBand? band, DateTime at) {
    final cue = switch (band) {
      PaceBand.tooSlow => PaceCue.tooSlow,
      PaceBand.tooFast => PaceCue.tooFast,
      PaceBand.onPace || null => null,
    };
    if (cue == null) return null;
    final last = _last;
    if (last != null && at.difference(last).inSeconds < kPaceCueGapSeconds) {
      return null;
    }
    _last = at;
    return cue;
  }

  /// Forgets the last cue, so the next off-pace fix speaks at once.
  void reset() => _last = null;
}
