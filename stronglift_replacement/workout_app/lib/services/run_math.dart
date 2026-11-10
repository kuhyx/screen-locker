/// Distance and moving-time maths for recorded tracks (pure, no I/O).
library;

import 'dart:math' as math;

import 'package:workout_app/models/run_track.dart';

/// Mean Earth radius in metres (IUGG), the haversine constant.
const double kEarthRadiusM = 6371008.8;

/// A pair of fixes further apart in time than this earns neither distance
/// nor moving time: a GPS dropout whose motion is unknown.
///
/// Mirrors `WALK_MAX_GAP_SECONDS` in the PC's `screen_locker/_constants.py`.
/// This is a mirror of the rule the PC applies to a walk's trackpoints, so the
/// app never reports moving time the PC would discard -- it is NOT a crediting
/// threshold (those stay on the PC).
const int kMaxCreditGapSeconds = 30;

/// A pair slower than this is standing still, not moving.
///
/// Mirrors `MIN_MOVING_SPEED_MPS` on the PC.
const double kMinMovingSpeedMps = 0.5;

/// Speed cap above which a fix is a GPS jump, 25 km/h for a run.
const double kRunningMaxSpeedMps = 25 / 3.6;

/// Speed cap above which a fix is a GPS jump, 8 km/h for a walk.
const double kWalkingMaxSpeedMps = 8 / 3.6;

/// The jump cap for [sport]. Display only: the PC's cap is 25 km/h for every
/// sport (`MAX_MOVING_SPEED_MPS`), so the walking cap here can show less than
/// the PC credits, never more.
double maxSpeedMps(RunSport sport) => switch (sport) {
  RunSport.running => kRunningMaxSpeedMps,
  RunSport.walking => kWalkingMaxSpeedMps,
};

double _rad(double degrees) => degrees * math.pi / 180;

/// Great-circle distance in metres between two WGS-84 positions.
double haversineM(double lat1, double lon1, double lat2, double lon2) {
  final dLat = _rad(lat2 - lat1);
  final dLon = _rad(lon2 - lon1);
  final a =
      math.pow(math.sin(dLat / 2), 2) +
      math.cos(_rad(lat1)) *
          math.cos(_rad(lat2)) *
          math.pow(math.sin(dLon / 2), 2);
  return 2 * kEarthRadiusM * math.asin(math.min(1, math.sqrt(a)));
}

/// Whether the step from [a] to [b] counts as moving: seen within
/// [kMaxCreditGapSeconds] and travelled at a speed in
/// `[kMinMovingSpeedMps, maxSpeed]`.
///
/// Speed comes from the cumulative `distanceM` difference, exactly as the PC
/// reads a TCX, so app and PC agree on which steps count.
bool isMovingStep(RunPoint a, RunPoint b, double maxSpeed) {
  final gap = b.time.difference(a.time).inMilliseconds / 1000;
  if (gap <= 0 || gap > kMaxCreditGapSeconds) return false;
  final speed = (b.distanceM - a.distanceM) / gap;
  return speed >= kMinMovingSpeedMps && speed <= maxSpeed;
}

/// Moving seconds over [points]: the summed gaps of every moving step.
int movingSeconds(List<RunPoint> points, RunSport sport) {
  final cap = maxSpeedMps(sport);
  var total = 0.0;
  for (var i = 1; i < points.length; i++) {
    if (isMovingStep(points[i - 1], points[i], cap)) {
      total += points[i].time.difference(points[i - 1].time).inSeconds;
    }
  }
  return total.round();
}
