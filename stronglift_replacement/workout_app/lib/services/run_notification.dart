/// The two lines of the ongoing run notification (numbers only, textgate).
library;

import 'package:workout_app/services/run_format.dart';

/// Distance as the title; moving time and average pace as the body.
({String title, String body}) runNotificationCopy({
  required double metres,
  required int movingSeconds,
}) => (
  title: formatDistanceKm(metres),
  body:
      '${formatDuration(movingSeconds)}  '
      '${formatPace(seconds: movingSeconds, distanceM: metres)}',
);
