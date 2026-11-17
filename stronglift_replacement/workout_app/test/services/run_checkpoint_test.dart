import 'dart:convert';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_phase.dart';

RunPoint _point(
  int i, {
  RunLink link = RunLink.continuous,
  double? altitude = 30,
}) => RunPoint(
  time: DateTime.utc(2026, 11, 9, 12).add(Duration(seconds: i * 2)),
  latitude: 48.8584 + i * 0.00002,
  longitude: 2.2945 - i * 0.000013,
  altitudeM: altitude,
  distanceM: i * 6.25,
  link: link,
);

RunCheckpoint _checkpoint({
  RunPhase phase = RunPhase.recording,
  List<RunPoint>? points,
  int? target = 330,
}) => RunCheckpoint(
  startedAt: DateTime.utc(2026, 11, 9, 11, 59, 58),
  savedAt: DateTime.utc(2026, 11, 9, 12, 5),
  phase: phase,
  points: points ?? [for (var i = 0; i < 4; i++) _point(i)],
  movingSeconds: 6,
  distanceM: 18.75,
  km: 0,
  segmentBreak: phase == RunPhase.paused,
  jumps: 2,
  paceTargetSeconds: target,
);

Map<String, Object?> _roundTripped(RunCheckpoint c) =>
    jsonDecode(jsonEncode(c.toJson())) as Map<String, Object?>;

void _expectSame(RunCheckpoint a, RunCheckpoint b) {
  expect(b.id, a.id);
  expect(b.startedAt, a.startedAt);
  expect(b.savedAt, a.savedAt);
  expect(b.phase, a.phase);
  expect(b.points, a.points);
  expect(b.movingSeconds, a.movingSeconds);
  expect(b.distanceM, a.distanceM);
  expect(b.km, a.km);
  expect(b.segmentBreak, a.segmentBreak);
  expect(b.jumps, a.jumps);
  expect(b.paceTargetSeconds, a.paceTargetSeconds);
}

void main() {
  group('round trip through JSON text', () {
    test('a recording checkpoint', () {
      final c = _checkpoint();
      _expectSame(c, RunCheckpoint.fromJson(_roundTripped(c)));
    });

    test('a paused one with no pace target', () {
      final c = _checkpoint(phase: RunPhase.paused, target: null);
      final back = RunCheckpoint.fromJson(_roundTripped(c));
      _expectSame(c, back);
      expect(back.paceTargetSeconds, isNull);
    });

    test('a run that has no fix yet', () {
      final c = _checkpoint(points: const []);
      final back = RunCheckpoint.fromJson(_roundTripped(c));
      _expectSame(c, back);
      expect(back.id, '2026-11-09T11:59:58Z');
    });

    test('segment and bridge markers and a missing altitude survive', () {
      final c = _checkpoint(
        points: [
          _point(0),
          _point(1, link: RunLink.bridge, altitude: null),
          _point(2, link: RunLink.segmentStart),
        ],
      );
      final back = RunCheckpoint.fromJson(_roundTripped(c));
      expect(back.points[1].link, RunLink.bridge);
      expect(back.points[1].altitudeM, isNull);
      expect(back.points[2].link, RunLink.segmentStart);
      _expectSame(c, back);
    });

    test('the id is the first point time, like the saved track', () {
      expect(_checkpoint().id, '2026-11-09T12:00:00Z');
    });

    test('many random shapes survive (seeded)', () {
      final rng = Random(20261117);
      for (var n = 0; n < 200; n++) {
        final count = rng.nextInt(40);
        final points = [
          for (var i = 0; i < count; i++)
            RunPoint(
              time: DateTime.utc(
                2026,
                11,
                9,
                12,
              ).add(Duration(seconds: i * (1 + rng.nextInt(90)))),
              latitude: rng.nextDouble() * 180 - 90,
              longitude: rng.nextDouble() * 360 - 180,
              altitudeM: rng.nextBool() ? rng.nextDouble() * 4000 - 400 : null,
              distanceM: rng.nextDouble() * 50000,
              link: RunLink.values[rng.nextInt(RunLink.values.length)],
            ),
        ];
        final c = RunCheckpoint(
          startedAt: DateTime.utc(2026, 11, 9, 11, rng.nextInt(60)),
          savedAt: DateTime.utc(2026, 11, 9, 13, rng.nextInt(60)),
          phase: rng.nextBool() ? RunPhase.recording : RunPhase.paused,
          points: points,
          movingSeconds: rng.nextInt(20000),
          distanceM: rng.nextDouble() * 50000,
          km: rng.nextInt(50),
          segmentBreak: rng.nextBool(),
          jumps: rng.nextInt(5),
          paceTargetSeconds: rng.nextBool() ? 200 + rng.nextInt(400) : null,
        );
        _expectSame(c, RunCheckpoint.fromJson(_roundTripped(c)));
      }
    });
  });

  group('fromJson rejects bad data with a FormatException', () {
    final good = _roundTripped(_checkpoint());

    void rejects(String why, Map<String, Object?> Function() make) {
      test(why, () {
        expect(() => RunCheckpoint.fromJson(make()), throwsFormatException);
      });
    }

    rejects('an unknown version', () => {...good, 'v': 99});
    rejects('no version', () => {...good}..remove('v'));
    rejects('a missing field', () => {...good}..remove('moving'));
    rejects('a wrongly typed field', () => {...good, 'moving': 'six'});
    rejects('a bad start time', () => {...good, 'startedAt': 'yesterday'});
    rejects('a non-string start time', () => {...good, 'startedAt': 5});
    rejects('idle as the phase', () => {...good, 'phase': 'idle'});
    rejects('finished as the phase', () => {...good, 'phase': 'finished'});
    rejects('an unknown phase', () => {...good, 'phase': 'dancing'});
    rejects('points that are not a list', () => {...good, 'points': 'many'});
    rejects(
      'a point that is not a list',
      () => {
        ...good,
        'points': [5],
      },
    );
    rejects(
      'a short point',
      () => {
        ...good,
        'points': [
          [1, 2.0],
        ],
      },
    );
    rejects(
      'a point with a text coordinate',
      () => {
        ...good,
        'points': [
          [1, 'x', 2.0, null, 3.0, 0],
        ],
      },
    );
    rejects(
      'a point with a bad altitude',
      () => {
        ...good,
        'points': [
          [1, 1.0, 2.0, 'high', 3.0, 0],
        ],
      },
    );
    rejects(
      'a point with an unknown link',
      () => {
        ...good,
        'points': [
          [1, 1.0, 2.0, null, 3.0, 7],
        ],
      },
    );
    rejects('a non-numeric pace target', () => {...good, 'target': 'fast'});
    rejects('a non-bool segment break', () => {...good, 'segBreak': 1});
  });
}
