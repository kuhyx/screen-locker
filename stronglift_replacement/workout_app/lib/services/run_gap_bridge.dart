/// When a straight line across a gap in the fixes may credit distance.
///
/// A gap is any stretch over `kMaxCreditGapSeconds` between two accepted fixes
/// that the runner did not pause: the phone died and was restored, or GPS
/// dropped out. The recorder always draws the line from the last fix before
/// the gap to the first one after it; it credits the distance (and the gap's
/// time as moving time) only when the implied pace is a plausible run.
library;

/// Fastest pace a bridge may credit, in seconds per kilometre (2:30 min/km).
/// Faster is a vehicle: the line is drawn, nothing is credited.
const int kBridgeFastestSecPerKm = 150;

/// Slowest pace a bridge may credit, in seconds per kilometre (12:00 min/km).
/// Slower is standing about, not a run.
const int kBridgeSlowestSecPerKm = 720;

/// The slowest speed a credited bridge can have, in metres per second.
const double kBridgeMinSpeedMps = 1000 / kBridgeSlowestSecPerKm;

/// Whether a bridge of [stepM] straight-line metres over [gapSeconds] is
/// credited: its pace lies within 2:30 and 12:00 min/km, bounds included.
bool bridgeCredits({required double stepM, required int gapSeconds}) {
  if (stepM <= 0 || gapSeconds <= 0) return false;
  final secPerKm = gapSeconds * 1000 / stepM;
  return secPerKm >= kBridgeFastestSecPerKm &&
      secPerKm <= kBridgeSlowestSecPerKm;
}
