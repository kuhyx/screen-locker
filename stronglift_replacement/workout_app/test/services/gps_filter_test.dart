import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/run_math.dart';

/// One degree of latitude in metres, so tests can place fixes by distance.
const double _degM = 111194.9;

GpsFix _fix(
  int seconds,
  double northM, {
  double accuracy = 5,
  bool mocked = false,
  int millis = 0,
}) => GpsFix(
  time: DateTime.utc(2026, 11, 9, 12, 0, seconds, millis),
  latitude: 48.8584 + northM / _degM,
  longitude: 2.2945,
  altitudeM: 30,
  accuracyM: accuracy,
  isMocked: mocked,
);

void main() {
  group('rejections', () {
    test('mocked fixes are dropped', () {
      final f = GpsFilter();
      expect(f.add(_fix(0, 0, mocked: true)), FixVerdict.mocked);
      expect(f.points, isEmpty);
    });

    test('accuracy above 25 m, negative or NaN is dropped', () {
      final f = GpsFilter();
      expect(f.add(_fix(0, 0, accuracy: 25.1)), FixVerdict.inaccurate);
      expect(f.add(_fix(0, 0, accuracy: -1)), FixVerdict.inaccurate);
      expect(f.add(_fix(0, 0, accuracy: double.nan)), FixVerdict.inaccurate);
      expect(f.add(_fix(0, 0, accuracy: 25)), FixVerdict.accepted);
    });

    test('same-second and older fixes are out of order', () {
      final f = GpsFilter()..add(_fix(10, 0));
      expect(f.add(_fix(10, 5, millis: 900)), FixVerdict.outOfOrder);
      expect(f.add(_fix(9, 5)), FixVerdict.outOfOrder);
      expect(f.points, hasLength(1));
    });

    test('a jump above the 25 km/h cap is dropped, below it kept', () {
      final f = GpsFilter()..add(_fix(0, 0));
      // 7.0 m/s > 25 km/h (6.94 m/s)
      expect(f.add(_fix(10, 70)), FixVerdict.tooFast);
      expect(f.add(_fix(20, 60)), FixVerdict.accepted);
    });

    test('one cap for everything: a 3 m/s stroll or sprint is no jump', () {
      // 3 m/s was over the old 8 km/h walking cap; it is a plain run now.
      final f = GpsFilter()..add(_fix(0, 0));
      expect(f.add(_fix(10, 30)), FixVerdict.accepted);
      expect(f.distanceM, closeTo(30, 0.5));
    });

    test('five consecutive jumps re-anchor without crediting distance', () {
      final f = GpsFilter()..add(_fix(0, 0));
      for (var i = 1; i < kMaxConsecutiveJumps; i++) {
        expect(f.add(_fix(i * 5, 5000)), FixVerdict.tooFast);
      }
      expect(f.add(_fix(25, 5000)), FixVerdict.accepted);
      expect(f.distanceM, 0);
      expect(f.add(_fix(35, 5010)), FixVerdict.accepted);
      expect(f.distanceM, closeTo(10, 0.1));
    });

    test('an accepted fix resets the jump counter', () {
      final f = GpsFilter()..add(_fix(0, 0));
      for (var i = 1; i < kMaxConsecutiveJumps; i++) {
        f.add(_fix(i * 5, 5000));
      }
      f.add(_fix(30, 20)); // good fix, resets
      expect(f.add(_fix(35, 5000)), FixVerdict.tooFast);
    });
  });

  group('distance credit', () {
    test('moving steps accumulate haversine distance', () {
      final f = GpsFilter();
      for (var i = 0; i < 4; i++) {
        f.add(_fix(i * 10, i * 27.0));
      }
      expect(f.distanceM, closeTo(81, 0.2));
      expect(f.points.last.distanceM, f.distanceM);
      expect(f.points.first.distanceM, 0);
      expect(f.points.first.altitudeM, 30);
    });

    test('standing-still jitter and a long dropout earn no distance', () {
      final f = GpsFilter()
        ..add(_fix(0, 0))
        ..add(_fix(10, 2)); // 0.2 m/s: standing
      expect(f.distanceM, 0);
      f.add(_fix(60, 100)); // 50 s later: unseen motion
      expect(f.distanceM, 0);
      f.add(_fix(70, 127)); // seen again, moving
      expect(f.distanceM, closeTo(27, 0.2));
      expect(f.points, hasLength(4));
    });

    test('times are truncated to whole UTC seconds', () {
      final f = GpsFilter()..add(_fix(3, 0, millis: 750));
      expect(f.points.single.time, DateTime.utc(2026, 11, 9, 12, 0, 3));
    });

    test('points is a read-only view and distance starts at zero', () {
      final f = GpsFilter();
      expect(f.distanceM, 0);
      f.add(_fix(0, 0));
      expect(() => f.points.clear(), throwsUnsupportedError);
    });
  });

  group('consistency with movingSeconds', () {
    test('every credited step is a moving step and vice versa', () {
      final f = GpsFilter();
      var north = 0.0;
      for (var s = 0; s <= 300; s += 10) {
        // walk 1.4 m/s, stand 40-70 s, resume
        final standing = s > 100 && s <= 140;
        if (!standing) north += 14;
        f.add(_fix(s, north));
      }
      expect(movingSeconds(f.points), 260);
    });
  });

  group('breakSegment', () {
    test('the fix after a pause earns nothing, then crediting resumes', () {
      final f = GpsFilter()
        ..add(_fix(0, 0))
        ..add(_fix(10, 14))
        ..breakSegment();
      // 20 s later and 28 m further: a moving step if not for the pause.
      expect(f.add(_fix(30, 42)), FixVerdict.accepted);
      expect(f.distanceM, closeTo(14, 0.5));
      expect(f.add(_fix(40, 56)), FixVerdict.accepted);
      expect(f.distanceM, closeTo(28, 0.5));
    });

    test('a pause jump is re-anchored, not rejected as a GPS jump', () {
      final f = GpsFilter()
        ..add(_fix(0, 0))
        ..breakSegment();
      expect(f.add(_fix(5, 5000)), FixVerdict.accepted);
      expect(f.distanceM, 0);
    });
  });
}
