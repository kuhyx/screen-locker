/// Turns raw GPS fixes into the accepted points of a track.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_math.dart';

/// Worst horizontal accuracy (metres, 68 % radius) a fix may report.
const double kMaxFixAccuracyM = 25;

/// Consecutive "too fast" fixes after which the filter concludes its anchor
/// was the bad one and re-anchors on the newest fix.
const int kMaxConsecutiveJumps = 5;

/// One reading from the platform's location provider.
@immutable
class GpsFix {
  /// Creates a fix.
  const GpsFix({
    required this.time,
    required this.latitude,
    required this.longitude,
    required this.accuracyM,
    this.altitudeM,
    this.isMocked = false,
  });

  /// When the provider took the fix.
  final DateTime time;

  /// Degrees north.
  final double latitude;

  /// Degrees east.
  final double longitude;

  /// Metres above sea level, when known.
  final double? altitudeM;

  /// Horizontal accuracy radius in metres.
  final double accuracyM;

  /// Whether Android flagged the fix as coming from a mock provider.
  final bool isMocked;
}

/// Why [GpsFilter.add] kept or dropped a fix.
enum FixVerdict {
  /// Kept as a new point.
  accepted,

  /// Dropped: a mock-location fix (faking a run must not credit it).
  mocked,

  /// Dropped: accuracy worse than [kMaxFixAccuracyM], or not a number.
  inaccurate,

  /// Dropped: not strictly later (whole seconds) than the last point.
  outOfOrder,

  /// Dropped: implies a speed above [kRunningMaxSpeedMps], i.e. a GPS jump.
  tooFast,
}

/// Accumulates accepted points and their cumulative credited distance.
///
/// A step between two accepted points adds its straight-line distance only
/// when it is a moving step (see [isMovingStep]). A signal dropout (a gap over
/// [kMaxCreditGapSeconds] with no pause) is bridged the way RunnerUp's export
/// bridges it, provided it implies [kMinDropoutSpeedMps] or faster; anything
/// above the jump cap is rejected, and standing-still jitter credits nothing.
/// A user pause ([breakSegment]) never bridges: pauses earn nothing.
class GpsFilter {
  /// Creates a filter; every recording uses the running jump cap.
  GpsFilter();

  final List<RunPoint> _points = [];
  int _jumps = 0;
  bool _segmentBreak = false;

  /// Accepted points so far, in time order.
  List<RunPoint> get points => List.unmodifiable(_points);

  /// Cumulative credited distance in metres.
  double get distanceM => _points.isEmpty ? 0 : _points.last.distanceM;

  /// Marks a pause: the next accepted fix starts a new segment, credited with
  /// nothing, whatever distance separates it from the last point.
  ///
  /// Without this, a short pause (under [kMaxCreditGapSeconds]) would credit
  /// the walk across the paused stretch, and a long one could trip the jump
  /// cap on the first fix after resuming.
  void breakSegment() => _segmentBreak = true;

  /// Judges [fix]; an accepted fix is appended to [points].
  FixVerdict add(GpsFix fix) {
    if (fix.isMocked) return FixVerdict.mocked;
    if (!(fix.accuracyM >= 0 && fix.accuracyM <= kMaxFixAccuracyM)) {
      return FixVerdict.inaccurate;
    }
    // Whole seconds: that is all a TCX trackpoint can say.
    final time = DateTime.fromMillisecondsSinceEpoch(
      fix.time.millisecondsSinceEpoch ~/ 1000 * 1000,
      isUtc: true,
    );
    if (_points.isEmpty) {
      _accept(fix, time, 0);
      return FixVerdict.accepted;
    }
    final last = _points.last;
    final gap = time.difference(last.time).inSeconds;
    if (gap <= 0) return FixVerdict.outOfOrder;
    if (_segmentBreak) {
      _segmentBreak = false;
      _accept(fix, time, 0);
      return FixVerdict.accepted;
    }
    final step = haversineM(
      last.latitude,
      last.longitude,
      fix.latitude,
      fix.longitude,
    );
    if (step / gap > kRunningMaxSpeedMps) {
      _jumps++;
      if (_jumps < kMaxConsecutiveJumps) return FixVerdict.tooFast;
      // The anchor, not the fixes, was wrong: continue from here, no credit.
      _accept(fix, time, 0);
      return FixVerdict.accepted;
    }
    final moving = step / gap >= minStepSpeed(gap);
    _accept(fix, time, moving ? step : 0);
    return FixVerdict.accepted;
  }

  void _accept(GpsFix fix, DateTime time, double credited) {
    _jumps = 0;
    _points.add(
      RunPoint(
        time: time,
        latitude: fix.latitude,
        longitude: fix.longitude,
        altitudeM: fix.altitudeM,
        distanceM: distanceM + credited,
      ),
    );
  }
}
