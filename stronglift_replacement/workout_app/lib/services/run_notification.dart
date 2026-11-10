/// The two lines of the ongoing run notification (numbers only, textgate).
library;

import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/run_format.dart';

/// Distance as the title; moving time and average pace as the body, plus the
/// current pace (to the nearest [kPaceStep], so GPS jitter does not redraw it
/// every fix) when a pace target is on.
({String title, String body}) runNotificationCopy({
  required double metres,
  required int movingSeconds,
  double? currentPace,
}) {
  final average = formatPace(seconds: movingSeconds, distanceM: metres);
  final current = currentPace == null
      ? ''
      : '  ${formatPaceSeconds((currentPace / kPaceStep).round() * kPaceStep)}';
  return (
    title: formatDistanceKm(metres),
    body: '${formatDuration(movingSeconds)}  $average$current',
  );
}
