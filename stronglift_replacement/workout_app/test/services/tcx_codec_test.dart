@TestOn('vm')
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/tcx_codec.dart';

RunTrack _track({
  RunSport sport = RunSport.running,
  double? alt = 31.5,
  RunSource source = RunSource.app,
}) {
  final start = DateTime.utc(2026, 11, 9, 16, 30);
  return RunTrack.started(
    sport: sport,
    startedAt: start,
    totalSeconds: 20,
    distanceM: 27.5,
    source: source,
    points: [
      for (var i = 0; i < 3; i++)
        RunPoint(
          time: start.add(Duration(seconds: i * 10)),
          latitude: 48.8584 + i * 0.0001,
          longitude: 2.2945,
          altitudeM: alt,
          distanceM: i * 13.75,
        ),
    ],
  );
}

void main() {
  group('encodeTcx', () {
    test('writes the PC-facing structure and the source tag', () {
      final xml = encodeTcx(_track());
      expect(xml, contains('<Activity Sport="Running">'));
      expect(xml, contains('<Id>2026-11-09T16:30:00Z</Id>'));
      expect(xml, contains('<Lap StartTime="2026-11-09T16:30:00Z">'));
      expect(xml, contains('<TotalTimeSeconds>20</TotalTimeSeconds>'));
      expect(xml, contains('<DistanceMeters>27.500</DistanceMeters>'));
      expect(xml, contains('<Time>2026-11-09T16:30:10Z</Time>'));
      expect(xml, contains('<Name>$kRunSourceName</Name>'));
      expect(
        xml,
        contains(
          'xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"',
        ),
      );
    });

    test('omits AltitudeMeters when the point has none', () {
      expect(encodeTcx(_track(alt: null)), isNot(contains('AltitudeMeters')));
      expect(encodeTcx(_track()), contains('<AltitudeMeters>31.5<'));
    });

    test('is deterministic', () {
      expect(encodeTcx(_track()), encodeTcx(_track()));
    });
  });

  group('round trip', () {
    for (final sport in RunSport.values) {
      test('${sport.tcxName} survives encode -> decode', () {
        final original = _track(sport: sport);
        final back = decodeTcx(
          encodeTcx(original),
          fileName: tcxFilename(original, utcOffset: Duration.zero),
        );
        expect(back.id, original.id);
        expect(back.sport, sport);
        expect(back.startedAt, original.startedAt);
        expect(back.totalSeconds, 20);
        expect(back.distanceM, closeTo(27.5, 1e-9));
        expect(back.source, RunSource.app);
        expect(back.points, hasLength(3));
        for (final (i, p) in back.points.indexed) {
          final o = original.points[i];
          expect(p.time, o.time);
          expect(p.latitude, closeTo(o.latitude, 1e-7));
          expect(p.longitude, closeTo(o.longitude, 1e-7));
          expect(p.altitudeM, closeTo(o.altitudeM!, 0.05));
          expect(p.distanceM, closeTo(o.distanceM, 1e-3));
        }
      });
    }

    test('a point without altitude stays without', () {
      final back = decodeTcx(encodeTcx(_track(alt: null)));
      expect(back.points.every((p) => p.altitudeM == null), isTrue);
    });
  });

  group('tcxFilename', () {
    test('stamps LOCAL time (offset applied to the UTC start)', () {
      final t = _track();
      expect(
        tcxFilename(t, utcOffset: const Duration(hours: 1)),
        'RunnerUp_2026-11-09-17-30-00_Running.tcx',
      );
      expect(
        tcxFilename(
          _track(sport: RunSport.walking),
          utcOffset: const Duration(hours: 9, minutes: 45),
        ),
        'RunnerUp_2026-11-10-02-15-00_Walking.tcx',
      );
    });

    test('defaults to the device zone and keeps the shape', () {
      expect(
        tcxFilename(_track()),
        matches(r'^RunnerUp_\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d_Running\.tcx$'),
      );
    });
  });

  test('tcxSha256 is the hex SHA-256 of the text', () {
    expect(
      tcxSha256('abc'),
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });
}
