// The pace band: current pace over the last 30 s, the +-10 s band around the
// target, and the cue throttle. Pure Dart, no recorder.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/pace_band.dart';

final _t0 = DateTime.utc(2026, 11, 9, 12);

/// Points 2 s apart moving at [mps] for [count] fixes, cumulative distance.
List<RunPoint> _points(double mps, int count, {int startSecond = 0}) => [
  for (var i = 0; i < count; i++)
    RunPoint(
      time: _t0.add(Duration(seconds: startSecond + i * 2)),
      latitude: 48,
      longitude: 2,
      altitudeM: 0,
      distanceM: i * 2 * mps,
    ),
];

void main() {
  group('currentPaceSeconds', () {
    test('is the pace over the last 30 s of fixes', () {
      // 3 m/s is 333.3 s/km.
      final pace = currentPaceSeconds(_points(3, 40))!;
      expect(pace, closeTo(1000 / 3, 0.01));
    });

    test('only the trailing 30 s count: a slow start is forgotten', () {
      final slow = _points(2, 20); // 40 s at 2 m/s
      final last = slow.last;
      final fast = [
        for (var i = 1; i <= 20; i++)
          RunPoint(
            time: last.time.add(Duration(seconds: i * 2)),
            latitude: 48,
            longitude: 2,
            altitudeM: 0,
            distanceM: last.distanceM + i * 2 * 4.0,
          ),
      ];
      expect(
        currentPaceSeconds([...slow, ...fast])!,
        closeTo(250, 0.01), // 4 m/s
      );
    });

    test('warm-up: null until the window spans 20 s', () {
      expect(currentPaceSeconds(_points(3, 1)), isNull);
      expect(currentPaceSeconds(_points(3, 10)), isNull); // 18 s
      expect(currentPaceSeconds(_points(3, 11)), isNotNull); // 20 s
    });

    test('standing still is no pace (null), not "too slow"', () {
      expect(currentPaceSeconds(_points(0.1, 30)), isNull);
    });

    test('from skips points before a resume', () {
      final before = _points(3, 20);
      final after = [
        for (var i = 0; i < 20; i++)
          RunPoint(
            time: _t0.add(Duration(seconds: 44 + i * 2)),
            latitude: 48,
            longitude: 2,
            altitudeM: 0,
            // A pause adds time but no distance.
            distanceM: before.last.distanceM + i * 2 * 3.0,
          ),
      ];
      final all = [...before, ...after];
      final naive = currentPaceSeconds(all);
      final resumed = currentPaceSeconds(all, from: before.length);
      expect(resumed, closeTo(1000 / 3, 0.01));
      // The window is wholly after the pause here, so both agree...
      expect(naive, closeTo(1000 / 3, 0.01));
      // ...but a window straddling the pause does not.
      final straddle = [...before, ...after.take(3)];
      expect(
        currentPaceSeconds(straddle, from: before.length),
        isNull, // 3 points = 4 s, still warming up
      );
      expect(currentPaceSeconds(straddle)!, greaterThan(400));
    });

    test('a gap over 30 s leaves a single point: warm-up again', () {
      final pts = [..._points(3, 20), ..._points(3, 1, startSecond: 200)];
      expect(currentPaceSeconds(pts), isNull);
    });
  });

  group('paceBandOf', () {
    test('inside +-10 s inclusive is on pace', () {
      expect(paceBandOf(current: 300, target: 300), PaceBand.onPace);
      expect(paceBandOf(current: 310, target: 300), PaceBand.onPace);
      expect(paceBandOf(current: 290, target: 300), PaceBand.onPace);
    });

    test('over the band is too slow, under it too fast', () {
      expect(paceBandOf(current: 310.01, target: 300), PaceBand.tooSlow);
      expect(paceBandOf(current: 289.99, target: 300), PaceBand.tooFast);
    });

    test('no pace yet means no verdict', () {
      expect(paceBandOf(current: null, target: 300), isNull);
    });
  });

  group('PaceCueThrottle', () {
    test('silent while on pace or unknown', () {
      final throttle = PaceCueThrottle();
      expect(throttle.cueFor(PaceBand.onPace, _t0), isNull);
      expect(throttle.cueFor(null, _t0), isNull);
    });

    test('too slow and too fast give distinct cues', () {
      expect(PaceCueThrottle().cueFor(PaceBand.tooSlow, _t0), PaceCue.tooSlow);
      expect(PaceCueThrottle().cueFor(PaceBand.tooFast, _t0), PaceCue.tooFast);
    });

    test('at most once per 30 s while off pace', () {
      final throttle = PaceCueThrottle();
      expect(throttle.cueFor(PaceBand.tooSlow, _t0), PaceCue.tooSlow);
      expect(
        throttle.cueFor(PaceBand.tooSlow, _t0.add(const Duration(seconds: 29))),
        isNull,
      );
      expect(
        throttle.cueFor(PaceBand.tooSlow, _t0.add(const Duration(seconds: 30))),
        PaceCue.tooSlow,
      );
    });

    test('flipping from slow to fast inside 30 s is still throttled', () {
      final throttle = PaceCueThrottle()..cueFor(PaceBand.tooSlow, _t0);
      expect(
        throttle.cueFor(PaceBand.tooFast, _t0.add(const Duration(seconds: 10))),
        isNull,
      );
    });

    test('returning to the band stays silent and does not reset the gap', () {
      final throttle = PaceCueThrottle()..cueFor(PaceBand.tooSlow, _t0);
      final at = _t0.add(const Duration(seconds: 12));
      expect(throttle.cueFor(PaceBand.onPace, at), isNull);
      expect(
        throttle.cueFor(PaceBand.tooSlow, at.add(const Duration(seconds: 5))),
        isNull,
      );
    });

    test('reset forgets the last cue', () {
      final throttle = PaceCueThrottle()
        ..cueFor(PaceBand.tooSlow, _t0)
        ..reset();
      expect(throttle.cueFor(PaceBand.tooSlow, _t0), PaceCue.tooSlow);
    });
  });

  test('the target range is 3:00..12:00 in 5 s steps', () {
    expect(kMinPaceTarget, 180);
    expect(kMaxPaceTarget, 720);
    expect(kPaceStep, 5);
    expect(clampPaceTarget(100), 180);
    expect(clampPaceTarget(9999), 720);
    expect(clampPaceTarget(303), 305);
  });
}
