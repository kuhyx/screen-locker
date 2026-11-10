import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_format.dart';

void main() {
  test('distance is km with two decimals', () {
    expect(formatDistanceKm(5200), '5.20');
    expect(formatDistanceKm(0), '0.00');
    expect(formatDistanceKm(12345.6), '12.35');
  });

  test('duration is m:ss under an hour, h:mm:ss from it', () {
    expect(formatDuration(0), '0:00');
    expect(formatDuration(65), '1:05');
    expect(formatDuration(3599), '59:59');
    expect(formatDuration(3600), '1:00:00');
    expect(formatDuration(3725), '1:02:05');
  });

  test('pace is m:ss per km, and a dash when nothing was covered', () {
    expect(formatPace(seconds: 1800, distanceM: 5000), '6:00');
    expect(formatPace(seconds: 1930, distanceM: 5200), '6:11');
    expect(formatPace(seconds: 100, distanceM: 9.9), '-:--');
    expect(formatPace(seconds: 100, distanceM: 0), '-:--');
  });

  test('dates are shown in local time', () {
    final when = DateTime(2026, 11, 3, 7, 5);
    expect(formatRunDay(when.toUtc()), '03.11');
    expect(formatFullDate(when.toUtc()), '2026-11-03 07:05');
  });
}
