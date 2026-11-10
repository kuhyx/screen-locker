/// Number formatting for run tiles and the run detail screen.
///
/// Numbers only: textgate bans words in the UI, so there are no unit
/// suffixes. The icon next to a value (distance, clock, pace) names it.
library;

String _two(int v) => v.toString().padLeft(2, '0');

/// Kilometres with two decimals, e.g. `5.20`.
String formatDistanceKm(double distanceM) =>
    (distanceM / 1000).toStringAsFixed(2);

/// `m:ss`, or `h:mm:ss` from an hour up; [seconds] is moving time.
String formatDuration(int seconds) {
  final h = seconds ~/ 3600;
  final m = (seconds ~/ 60).remainder(60);
  final s = seconds % 60;
  return h > 0 ? '$h:${_two(m)}:${_two(s)}' : '$m:${_two(s)}';
}

/// Average pace as `m:ss` per kilometre, or `-:--` when under 10 m was
/// covered (the quotient is meaningless, and 0 would divide by zero).
String formatPace({required int seconds, required double distanceM}) {
  if (distanceM < 10) return '-:--';
  return formatPaceSeconds((seconds / (distanceM / 1000)).round());
}

/// A pace of [perKm] seconds per kilometre as `m:ss`.
String formatPaceSeconds(int perKm) => '${perKm ~/ 60}:${_two(perKm % 60)}';

/// `dd.MM` of [when] in the device's local time.
String formatRunDay(DateTime when) {
  final l = when.toLocal();
  return '${_two(l.day)}.${_two(l.month)}';
}

/// `yyyy-MM-dd HH:mm` of [when] in the device's local time.
String formatFullDate(DateTime when) {
  final l = when.toLocal();
  return '${l.year}-${_two(l.month)}-${_two(l.day)} '
      '${_two(l.hour)}:${_two(l.minute)}';
}
