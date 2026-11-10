import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_math.dart';

RunPoint _p(int seconds, double distanceM) => RunPoint(
  time: DateTime.utc(2026, 11, 9, 12, 0, seconds),
  latitude: 0,
  longitude: 0,
  distanceM: distanceM,
);

void main() {
  group('haversineM', () {
    test('is zero for the same point', () {
      expect(haversineM(48.85, 2.29, 48.85, 2.29), 0);
    });

    test('one degree of latitude is about 111.2 km', () {
      expect(haversineM(0, 0, 1, 0), closeTo(111195, 5));
    });

    test('is symmetric and shrinks east-west away from the equator', () {
      final a = haversineM(60, 0, 60, 1);
      expect(a, haversineM(60, 1, 60, 0));
      expect(a, closeTo(55597, 20));
    });

    test('antipodes stay finite (clamped asin argument)', () {
      expect(haversineM(0, 0, 0, 180), closeTo(20015087, 50));
    });
  });

  group('kRunningMaxSpeedMps', () {
    test('the one jump cap is 25 km/h', () {
      expect(kRunningMaxSpeedMps, closeTo(25 / 3.6, 1e-9));
    });
  });

  group('isMovingStep / movingSeconds', () {
    const cap = 3.0;

    test('a normal step counts', () {
      expect(isMovingStep(_p(0, 0), _p(10, 13), cap), isTrue);
    });

    test('standing still, too fast and non-forward steps do not', () {
      expect(isMovingStep(_p(0, 0), _p(10, 4), cap), isFalse);
      expect(isMovingStep(_p(0, 0), _p(10, 40), cap), isFalse);
      expect(isMovingStep(_p(5, 0), _p(5, 10), cap), isFalse);
      expect(isMovingStep(_p(10, 0), _p(5, 10), cap), isFalse);
    });

    test('a gap over 30 s earns nothing, 30 s exactly does', () {
      expect(isMovingStep(_p(0, 0), _p(30, 40), cap), isTrue);
      expect(isMovingStep(_p(0, 0), _p(31, 40), cap), isFalse);
    });

    test('movingSeconds sums only the moving steps', () {
      final points = [
        _p(0, 0),
        _p(10, 13), // moving, 10 s
        _p(20, 13), // standing, 0 distance
        _p(55, 60), // 35 s gap, not credited
        _p(65, 73), // moving, 10 s
      ];
      expect(movingSeconds(points), 20);
      expect(movingSeconds(const []), 0);
    });
  });
}
