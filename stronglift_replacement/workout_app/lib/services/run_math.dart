/// Distance and moving-time maths for recorded tracks (pure, no I/O).
///
/// The PC's one crediting rule (`screen_locker/_activity_day.py`, `_walk_tcx.py`),
/// for every GPS activity whatever its sport: a day's activities are summed and
/// count once the distance reaches 3.5 km (5 % tolerance) OR the moving time
/// reaches 25 min. Only the PC decides that; the app has no "qualifies" test.
///
/// The PC judges speed over windows of at least 10 s (`TRACK_WINDOW_SECONDS`).
/// A window faster than 25 km/h earns neither distance nor time; a window of
/// 30 s or less earns moving time at 0.5 m/s or faster; a longer one (a GPS
/// dropout) at 1 m/s or faster; paused time earns nothing.
///
/// The app mirrors only the bounds, per pair of its 2 s fixes, and is stricter:
/// a pair over 30 s credits nothing, where the PC keeps a dropout at 1 m/s or
/// faster. The app writes zero distance across such a gap, so the PC does not
/// credit a dropout in an app-recorded run. Its on-screen moving time is
/// therefore an estimate, not the number the PC will credit.
library;

import 'dart:math' as math;

import 'package:workout_app/models/run_track.dart';

/// Mean Earth radius in metres (IUGG), the haversine constant.
const double kEarthRadiusM = 6371008.8;

/// A pair of fixes further apart in time than this earns neither distance
/// nor moving time: a GPS dropout whose motion is unknown.
///
/// Mirrors `WALK_MAX_GAP_SECONDS` in the PC's `screen_locker/_constants.py`.
const int kMaxCreditGapSeconds = 30;

/// A pair slower than this is standing still, not moving.
///
/// Mirrors `MIN_MOVING_SPEED_MPS` on the PC.
const double kMinMovingSpeedMps = 0.5;

/// Speed cap above which a fix is a GPS jump, 25 km/h.
///
/// Mirrors `MAX_MOVING_SPEED_MPS` on the PC, which applies it to each window
/// of 10 s or more rather than to each fix. One cap for every recording: the
/// PC credits every GPS activity with the same rule.
const double kRunningMaxSpeedMps = 25 / 3.6;

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
/// Speed comes from the cumulative `distanceM` difference, as the PC reads a
/// TCX, but over one pair of fixes rather than a window of 10 s or more, so the
/// two can disagree on a jittery or stop-and-go stretch.
bool isMovingStep(RunPoint a, RunPoint b, double maxSpeed) {
  final gap = b.time.difference(a.time).inMilliseconds / 1000;
  if (gap <= 0 || gap > kMaxCreditGapSeconds) return false;
  final speed = (b.distanceM - a.distanceM) / gap;
  return speed >= kMinMovingSpeedMps && speed <= maxSpeed;
}

/// Moving seconds over [points]: the summed gaps of every moving step.
int movingSeconds(List<RunPoint> points) {
  var total = 0.0;
  for (var i = 1; i < points.length; i++) {
    if (isMovingStep(points[i - 1], points[i], kRunningMaxSpeedMps)) {
      total += points[i].time.difference(points[i - 1].time).inSeconds;
    }
  }
  return total.round();
}
