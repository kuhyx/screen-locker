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

    test('30 s exactly needs 0.5 m/s, a longer dropout needs 1 m/s', () {
      expect(isMovingStep(_p(0, 0), _p(30, 40), cap), isTrue);
      expect(isMovingStep(_p(0, 0), _p(30, 16), cap), isTrue);
      // 31 s at 0.65 m/s: a pause-like stand, not a bridged dropout.
      expect(isMovingStep(_p(0, 0), _p(31, 20), cap), isFalse);
      // 60 s at 1 m/s and at 3 m/s: bridged dropouts.
      expect(isMovingStep(_p(0, 0), _p(60, 60), cap), isTrue);
      expect(isMovingStep(_p(0, 0), _p(60, 180), cap), isTrue);
      // A dropout faster than the cap or with no distance (pause) is not.
      expect(isMovingStep(_p(0, 0), _p(60, 400), cap), isFalse);
      expect(isMovingStep(_p(0, 0), _p(60, 0), cap), isFalse);
    });

    test('movingSeconds sums only the moving steps', () {
      final points = [
        _p(0, 0),
        _p(10, 13), // moving, 10 s
        _p(20, 13), // standing, 0 distance
        _p(55, 23), // 35 s gap at 0.29 m/s, not credited
        _p(65, 36), // moving, 10 s
        _p(125, 216), // 60 s dropout at 3 m/s, bridged
      ];
      expect(movingSeconds(points), 80);
      expect(movingSeconds(const []), 0);
    });
  });
}
