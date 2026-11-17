/// Turns raw GPS fixes into the accepted points of a track.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_gap_bridge.dart';
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
/// A step between two accepted points adds distance only when it is a moving
/// step (see [isMovingStep]): standing-still jitter credits nothing. A gap
/// over [kMaxCreditGapSeconds] (phone dead, GPS dropout) is bridged by a
/// straight line, always kept, credited only at a plausible pace
/// ([bridgeCredits]); the jump cap does not apply across it.
class GpsFilter {
  /// Creates a filter; every recording uses the running jump cap.
  GpsFilter();

  /// Rebuilds a filter from a checkpoint: the [points] so far, whether a
  /// pause is still waiting for its next fix, and the jump count.
  GpsFilter.restore({
    required List<RunPoint> points,
    this._segmentBreak = false,
    this._jumps = 0,
  }) {
    _points.addAll(points);
  }

  final List<RunPoint> _points = [];
  int _jumps = 0;
  bool _segmentBreak = false;

  /// Accepted points so far, in time order.
  List<RunPoint> get points => List.unmodifiable(_points);

  /// Whether the next accepted fix starts a new segment (a pause is open).
  bool get segmentBreak => _segmentBreak;

  /// Consecutive too-fast fixes seen since the last accepted one.
  int get jumps => _jumps;

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
      _accept(fix, time, 0, RunLink.continuous);
      return FixVerdict.accepted;
    }
    final last = _points.last;
    final gap = time.difference(last.time).inSeconds;
    if (gap <= 0) return FixVerdict.outOfOrder;
    if (_segmentBreak) {
      _segmentBreak = false;
      _accept(fix, time, 0, RunLink.segmentStart);
      return FixVerdict.accepted;
    }
    final step = haversineM(
      last.latitude,
      last.longitude,
      fix.latitude,
      fix.longitude,
    );
    if (gap > kMaxCreditGapSeconds) {
      final credited = bridgeCredits(stepM: step, gapSeconds: gap);
      _accept(fix, time, credited ? step : 0, RunLink.bridge);
      return FixVerdict.accepted;
    }
    if (step / gap > kRunningMaxSpeedMps) {
      _jumps++;
      if (_jumps < kMaxConsecutiveJumps) return FixVerdict.tooFast;
      // The anchor, not the fixes, was wrong: continue from here, no credit.
      _accept(fix, time, 0, RunLink.segmentStart);
      return FixVerdict.accepted;
    }
    final moving = step / gap >= kMinMovingSpeedMps;
    _accept(fix, time, moving ? step : 0, RunLink.continuous);
    return FixVerdict.accepted;
  }

  void _accept(GpsFix fix, DateTime time, double credited, RunLink link) {
    _jumps = 0;
    _points.add(
      RunPoint(
        time: time,
        latitude: fix.latitude,
        longitude: fix.longitude,
        altitudeM: fix.altitudeM,
        distanceM: distanceM + credited,
        link: link,
      ),
    );
  }
}
