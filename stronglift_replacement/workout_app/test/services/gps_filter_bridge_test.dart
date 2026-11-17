import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/run_math.dart';

const double _degM = 111194.9;

GpsFix _fix(int seconds, double northM, {double accuracy = 5}) => GpsFix(
  time: DateTime.utc(2026, 11, 9, 12).add(Duration(seconds: seconds)),
  latitude: 48.8584 + northM / _degM,
  longitude: 2.2945,
  altitudeM: 30,
  accuracyM: accuracy,
);

GpsFilter _runningTo30m() => GpsFilter()
  ..add(_fix(0, 0))
  ..add(_fix(10, 30));

void main() {
  group('a gap over 30 s is bridged by a straight line', () {
    test('at 5:00/km the line is credited and flagged as a bridge', () {
      final f = _runningTo30m();
      expect(f.add(_fix(310, 30 + 1000)), FixVerdict.accepted);
      expect(f.distanceM, closeTo(1030, 1));
      expect(f.points.last.link, RunLink.bridge);
    });

    test('a bridge faster than 2:30/km is drawn but earns 0 m', () {
      final f = _runningTo30m();
      expect(f.add(_fix(70, 30 + 1000)), FixVerdict.accepted); // 60 s, 1 km
      expect(f.distanceM, closeTo(30, 0.5));
      expect(f.points.last.link, RunLink.bridge);
      expect(f.points.last.latitude, closeTo(48.8584 + 1030 / _degM, 1e-6));
    });

    test('a bridge slower than 12:00/km earns 0 m', () {
      final f = _runningTo30m()..add(_fix(1010, 30 + 100)); // 1000 s, 100 m
      expect(f.distanceM, closeTo(30, 0.5));
      expect(f.points.last.link, RunLink.bridge);
    });

    test('the jump cap does not reject the first fix after a gap', () {
      final f = _runningTo30m();
      expect(f.add(_fix(3610, 30 + 50000)), FixVerdict.accepted);
      expect(f.distanceM, closeTo(30, 0.5));
    });

    test('exactly 30 s is not a gap', () {
      final f = _runningTo30m()..add(_fix(40, 30 + 90)); // 30 s, 3 m/s
      expect(f.points.last.link, RunLink.continuous);
      expect(f.distanceM, closeTo(120, 0.5));
    });

    test('31 s is a gap and still credited at a running pace', () {
      final f = _runningTo30m()..add(_fix(41, 30 + 93));
      expect(f.points.last.link, RunLink.bridge);
      expect(f.distanceM, closeTo(123, 0.5));
    });

    test('a pause still earns nothing and is a segment start', () {
      final f = _runningTo30m()
        ..breakSegment()
        ..add(_fix(310, 30 + 1000));
      expect(f.distanceM, closeTo(30, 0.5));
      expect(f.points.last.link, RunLink.segmentStart);
    });

    test('moving time counts only a credited bridge', () {
      final credited = _runningTo30m()..add(_fix(310, 1030));
      expect(movingSeconds(credited.points), 10 + 300);
      final vehicle = _runningTo30m()..add(_fix(70, 1030));
      expect(movingSeconds(vehicle.points), 10);
    });
  });

  group('GpsFilter.restore', () {
    test('rebuilds points, segment break and jump count', () {
      final f = _runningTo30m()..breakSegment();
      final back = GpsFilter.restore(
        points: f.points,
        segmentBreak: f.segmentBreak,
        jumps: f.jumps,
      );
      expect(back.points, f.points);
      expect(back.segmentBreak, isTrue);
      expect(back.distanceM, f.distanceM);
      expect(back.add(_fix(310, 5000)), FixVerdict.accepted);
      expect(back.points.last.link, RunLink.segmentStart);
    });

    test('an empty restore behaves like a fresh filter', () {
      final back = GpsFilter.restore(points: const []);
      expect(back.distanceM, 0);
      expect(back.add(_fix(0, 0)), FixVerdict.accepted);
    });

    test('the jump count carries over', () {
      final back = GpsFilter.restore(
        points: _runningTo30m().points,
        jumps: kMaxConsecutiveJumps - 1,
      );
      // 4 earlier jumps + this one = 5: re-anchors instead of rejecting.
      expect(back.add(_fix(12, 30 + 1000)), FixVerdict.accepted);
      expect(back.points.last.link, RunLink.segmentStart);
    });
  });
}
