/// The sandbox's GPS: a synthetic loop replayed faster than real time.
///
/// There is no bundled asset (that would need a pubspec entry): the track is a
/// pure function of the start time, so every replay gets its own
/// `RunTrack.id` and two replays never collide in the `runs` table.
library;

import 'dart:math' as math;

import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/position_source_geolocator.dart';
import 'package:workout_app/services/position_source_scripted.dart';

/// Length of the synthetic loop in metres.
const double kLoopLengthM = 4000;

/// Seconds between replayed fixes (the real request interval).
const int kFixStepSeconds = 2;

// A neutral spot: nobody's home, any tile server has it.
const double _centreLat = 50;
const double _centreLon = 10;

/// Pace of the replay: 10 km/h.
const double kReplaySpeedMps = 10 / 3.6;

/// Fixes for one lap of a [kLoopLengthM] circle starting at [start], one every
/// [kFixStepSeconds], 5 m accuracy.
List<GpsFix> sandboxLoopFixes(DateTime start) {
  const radius = kLoopLengthM / (2 * math.pi);
  final steps = (kLoopLengthM / kReplaySpeedMps / kFixStepSeconds).round();
  const metresPerDegree = 111194.9;
  final lonScale = metresPerDegree * math.cos(_centreLat * math.pi / 180);
  return [
    for (var i = 0; i <= steps; i++)
      GpsFix(
        time: start.add(Duration(seconds: i * kFixStepSeconds)),
        latitude:
            _centreLat +
            radius * math.sin(2 * math.pi * i / steps) / metresPerDegree,
        longitude:
            _centreLon +
            radius * (1 - math.cos(2 * math.pi * i / steps)) / lonScale,
        accuracyM: 5,
      ),
  ];
}

/// The sandbox's [PositionSource]: the loop at [Sandbox.runReplayFactor] times
/// real speed, starting now.
PositionSource sandboxRunSource({DateTime? now}) => ScriptedPositionSource(
  sandboxLoopFixes(now ?? DateTime.now()),
  fixDelay: Duration(
    microseconds: kFixStepSeconds * 1000000 ~/ Sandbox.runReplayFactor,
  ),
);

/// The source a recording uses: the replay in the sandbox, the phone's GPS
/// otherwise.
PositionSource positionSourceFor() =>
    Sandbox.enabled ? sandboxRunSource() : GeolocatorPositionSource();

/// The source the idle map watches: in the sandbox just the replay's first
/// fix (so the marker sits at the loop's start and does not walk the lap
/// before the run), the phone's GPS otherwise.
PositionSource idlePositionSourceFor({DateTime? now}) => Sandbox.enabled
    ? ScriptedPositionSource([sandboxLoopFixes(now ?? DateTime.now()).first])
    : GeolocatorPositionSource();
