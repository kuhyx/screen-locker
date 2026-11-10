/// Number formatting for the live run screen and its notification.
///
/// Numbers only (textgate): the digits are the whole display.
library;

/// Distance below which a pace means nothing (GPS noise at the start line).
const double kMinPaceDistanceM = 20;

/// `m:ss`, or `h:mm:ss` from one hour on.
String formatDuration(int seconds) {
  final s = seconds < 0 ? 0 : seconds;
  String two(int v) => v.toString().padLeft(2, '0');
  final h = s ~/ 3600;
  final m = s % 3600 ~/ 60;
  return h > 0 ? '$h:${two(m)}:${two(s % 60)}' : '$m:${two(s % 60)}';
}

/// Kilometres with two decimals, e.g. `3.52`.
String formatKm(double metres) => (metres / 1000).toStringAsFixed(2);

/// Average pace in seconds per km, or null while the run is too short.
double? paceSecPerKm(int movingSeconds, double metres) =>
    metres < kMinPaceDistanceM ? null : movingSeconds / (metres / 1000);

/// `m:ss` per km, or `--:--` while there is no pace yet.
String formatPace(double? secPerKm) =>
    secPerKm == null || secPerKm.isInfinite || secPerKm.isNaN
    ? '--:--'
    : formatDuration(secPerKm.round());

/// The two notification lines: distance, then time and pace.
({String title, String body}) runNotificationCopy({
  required double metres,
  required int movingSeconds,
}) => (
  title: formatKm(metres),
  body:
      '${formatDuration(movingSeconds)}  '
      '${formatPace(paceSecPerKm(movingSeconds, metres))}',
);
