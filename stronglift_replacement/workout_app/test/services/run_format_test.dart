import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_format.dart';

void main() {
  test('durations are m:ss, then h:mm:ss, never negative', () {
    expect(formatDuration(0), '0:00');
    expect(formatDuration(723), '12:03');
    expect(formatDuration(3600), '1:00:00');
    expect(formatDuration(3725), '1:02:05');
    expect(formatDuration(-4), '0:00');
  });

  test('distance is kilometres with two decimals', () {
    expect(formatKm(0), '0.00');
    expect(formatKm(3524), '3.52');
  });

  test('pace needs 20 m and is m:ss per km', () {
    expect(paceSecPerKm(10, 19.9), isNull);
    expect(paceSecPerKm(312, 1000), 312);
    expect(formatPace(312), '5:12');
    expect(formatPace(null), '--:--');
    expect(formatPace(double.infinity), '--:--');
    expect(formatPace(double.nan), '--:--');
  });

  test('the notification is numbers only', () {
    final copy = runNotificationCopy(metres: 3524, movingSeconds: 723);
    expect(copy.title, '3.52');
    expect(copy.body, '12:03  3:25');
    expect(
      runNotificationCopy(metres: 0, movingSeconds: 0).body,
      '0:00  --:--',
    );
  });
}
